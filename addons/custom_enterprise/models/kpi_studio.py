from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CustomKpiSnapshot(models.Model):
    _name = "custom.kpi.snapshot"
    _description = "Executive Cross-ERP KPI Snapshot"
    _order = "snapshot_date desc, id desc"

    name = fields.Char(required=True, default=lambda self: f"KPI Snapshot {fields.Date.today()}")
    snapshot_date = fields.Date(default=fields.Date.context_today, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    sales_30d = fields.Monetary(string="30-Day Confirmed Sales", readonly=True)
    gross_margin_30d = fields.Monetary(string="30-Day Gross Margin", readonly=True)
    cod_orders_30d = fields.Integer(string="30-Day COD Orders", readonly=True)
    rto_orders_30d = fields.Integer(string="30-Day RTO Orders", readonly=True)
    rto_rate_pct = fields.Float(string="RTO Rate (%)", readonly=True)
    active_subscriptions = fields.Integer(string="Active Subscriptions", readonly=True)
    monthly_mrr = fields.Monetary(string="Active MRR", readonly=True)
    open_tickets = fields.Integer(string="Open Helpdesk Tickets", readonly=True)
    sla_breached_tickets = fields.Integer(string="SLA Breached Tickets", readonly=True)
    pending_approvals = fields.Integer(string="Pending Approvals", readonly=True)
    asset_net_book_value = fields.Monetary(string="Fixed Assets Net Book Value", readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    def action_refresh_kpis(self):
        cutoff = fields.Datetime.now() - timedelta(days=30)
        SaleOrder = self.env["sale.order"]
        Ticket = self.env["custom.support.ticket"]
        Sub = self.env["custom.subscription"]
        Asset = self.env["custom.asset"]
        Approval = self.env["custom.approval.request"]

        for snap in self:
            orders = SaleOrder.search([
                ("company_id", "=", snap.company_id.id),
                ("state", "=", "sale"),
                ("date_order", ">=", cutoff),
            ])
            total_sales = sum(orders.mapped("amount_total"))
            total_margin = sum(orders.mapped("margin"))
            cod_count = len(orders.filtered(lambda o: o.x_payment_mode == "cod"))
            rto_count = len(orders.filtered(lambda o: o.x_is_rto))
            subs = Sub.search([("company_id", "=", snap.company_id.id), ("state", "=", "active")])
            assets = Asset.search([("company_id", "=", snap.company_id.id), ("state", "=", "running")])

            snap.write({
                "sales_30d": total_sales,
                "gross_margin_30d": total_margin,
                "cod_orders_30d": cod_count,
                "rto_orders_30d": rto_count,
                "rto_rate_pct": round((rto_count / len(orders) * 100.0), 2) if orders else 0.0,
                "active_subscriptions": len(subs),
                "monthly_mrr": sum(subs.mapped("mrr_amount")),
                "open_tickets": Ticket.search_count([("stage", "in", ("new", "in_progress", "waiting_customer"))]),
                "sla_breached_tickets": Ticket.search_count([("sla_status", "=", "breached"), ("stage", "not in", ("resolved", "closed"))]),
                "pending_approvals": Approval.search_count([("state", "=", "pending")]),
                "asset_net_book_value": sum(assets.mapped("book_value")),
            })


class CustomStudioFieldWizard(models.TransientModel):
    _name = "custom.studio.field.wizard"
    _description = "Studio-Lite Custom Field Builder"

    model_id = fields.Many2one(
        "ir.model",
        string="Target Model",
        required=True,
        domain="[('model', 'in', ('sale.order', 'product.template', 'res.partner', 'stock.picking', 'crm.lead', 'account.move', 'custom.support.ticket'))]",
    )
    field_name = fields.Char(
        string="Technical Field Name",
        required=True,
        default="x_studio_",
        help="Must start with x_ (for example x_studio_whatsapp_optin).",
    )
    field_label = fields.Char(string="Field Label", required=True)
    ttype = fields.Selection(
        [
            ("char", "Text (Char)"),
            ("text", "Multiline Text"),
            ("boolean", "Checkbox (Boolean)"),
            ("integer", "Integer"),
            ("float", "Decimal (Float)"),
            ("date", "Date"),
        ],
        default="char",
        required=True,
        string="Field Type",
    )
    add_to_default_form = fields.Boolean(
        string="Auto-Add Field to Model's Main Form View",
        default=True,
    )

    def action_create_field(self):
        self.ensure_one()
        fname = (self.field_name or "").strip()
        if not fname.startswith("x_"):
            raise UserError(_("Custom field technical names in Odoo must start with 'x_'."))
        IrField = self.env["ir.model.fields"].sudo()
        if IrField.search_count([("model_id", "=", self.model_id.id), ("name", "=", fname)]):
            raise UserError(_("Field '%s' already exists on %s.") % (fname, self.model_id.model))
        IrField.create({
            "model_id": self.model_id.id,
            "name": fname,
            "field_description": self.field_label,
            "ttype": self.ttype,
            "state": "manual",
        })
        if self.add_to_default_form:
            base_view = self.env["ir.ui.view"].sudo().search([
                ("model", "=", self.model_id.model),
                ("type", "=", "form"),
                ("mode", "=", "primary"),
            ], order="priority asc, id asc", limit=1)
            if base_view:
                self.env["ir.ui.view"].sudo().create({
                    "name": f"studio.lite.{self.model_id.model}.{fname}",
                    "model": self.model_id.model,
                    "inherit_id": base_view.id,
                    "type": "form",
                    "arch": (
                        f'<data><xpath expr="//sheet//group[last()]" position="inside">'
                        f'<field name="{fname}"/>'
                        f'</xpath></data>'
                    ),
                })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Custom Field Created"),
                "message": _("Added %s (%s) to %s.") % (self.field_label, fname, self.model_id.model),
                "type": "success",
                "sticky": False,
            },
        }

