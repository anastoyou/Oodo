from odoo import _, api, fields, models


class CustomSupportTicket(models.Model):
    _name = "custom.support.ticket"
    _description = "Customer Support & Size Exchange Ticket"
    _inherit = ["mail.thread", "mail.activity.mixin", "portal.mixin"]
    _order = "priority desc, id desc"

    name = fields.Char(
        string="Ticket #",
        required=True,
        copy=False,
        readonly=True,
        default="New",
    )
    subject = fields.Char(
        string="Subject",
        required=True,
        tracking=True,
    )
    description = fields.Text(
        string="Customer Message / Details",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        tracking=True,
        index=True,
    )
    contact_name = fields.Char(string="Contact Name")
    contact_email = fields.Char(string="Email")
    contact_phone = fields.Char(string="Phone / WhatsApp")
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Related Order",
        domain="[('partner_id', '=?', partner_id)]",
        tracking=True,
    )
    category = fields.Selection(
        selection=[
            ("size_exchange", "Size / Fit Exchange"),
            ("delivery_tracking", "Delivery / Tracking Status"),
            ("cod_verification", "COD Order Verification"),
            ("defect_damage", "Damaged / Incorrect Item"),
            ("return_refund", "Return & Refund Request"),
            ("payment_gst", "Payment / GST Invoice"),
            ("other", "General Inquiry"),
        ],
        string="Issue Type",
        default="size_exchange",
        required=True,
        tracking=True,
    )
    priority = fields.Selection(
        selection=[
            ("0", "Normal"),
            ("1", "Medium"),
            ("2", "High"),
            ("3", "Urgent"),
        ],
        string="Priority",
        default="1",
        tracking=True,
    )
    stage = fields.Selection(
        selection=[
            ("new", "New"),
            ("in_progress", "In Progress"),
            ("waiting_customer", "Waiting on Customer"),
            ("resolved", "Resolved"),
            ("closed", "Closed"),
        ],
        string="Stage",
        default="new",
        required=True,
        tracking=True,
        group_expand="_group_expand_stage",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Assigned Agent",
        tracking=True,
        domain="[('share', '=', False)]",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    resolution_notes = fields.Text(string="Resolution Summary")
    closed_date = fields.Datetime(string="Resolved / Closed At", readonly=True, copy=False)
    color = fields.Integer(string="Color Index")

    @api.model
    def _group_expand_stage(self, stages, domain):
        return [key for key, _label in self._fields["stage"].selection]

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.support.ticket") or "New"
            if vals.get("partner_id"):
                partner = self.env["res.partner"].browse(vals["partner_id"])
                vals.setdefault("contact_name", partner.name)
                vals.setdefault("contact_email", partner.email)
                vals.setdefault("contact_phone", partner.phone)
        return super().create(vals_list)

    def _compute_access_url(self):
        super()._compute_access_url()
        for ticket in self:
            ticket.access_url = f"/my/tickets/{ticket.id}"

    def action_assign_to_me(self):
        self.write({"user_id": self.env.user.id})

    def action_start_progress(self):
        self.write({"stage": "in_progress"})

    def action_wait_customer(self):
        self.write({"stage": "waiting_customer"})

    def action_resolve(self):
        self.write({"stage": "resolved", "closed_date": fields.Datetime.now()})

    def action_close(self):
        self.write({"stage": "closed", "closed_date": fields.Datetime.now()})

    def action_reopen(self):
        self.write({"stage": "in_progress", "closed_date": False})


class ResPartner(models.Model):
    _inherit = "res.partner"

    x_ticket_count = fields.Integer(
        string="Support Tickets",
        compute="_compute_x_ticket_count",
    )

    def _compute_x_ticket_count(self):
        grouped = self.env["custom.support.ticket"]._read_group(
            [("partner_id", "in", self.ids)],
            ["partner_id"],
            ["__count"],
        )
        counts = {partner.id: count for partner, count in grouped}
        for partner in self:
            partner.x_ticket_count = counts.get(partner.id, 0)

    def action_view_support_tickets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Support Tickets"),
            "res_model": "custom.support.ticket",
            "view_mode": "list,kanban,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {
                "default_partner_id": self.id,
                "default_contact_name": self.name,
                "default_contact_email": self.email,
                "default_contact_phone": self.phone,
            },
        }


class SaleOrderTicketLink(models.Model):
    _inherit = "sale.order"

    x_ticket_count = fields.Integer(
        string="Tickets",
        compute="_compute_x_ticket_count",
    )

    def _compute_x_ticket_count(self):
        grouped = self.env["custom.support.ticket"]._read_group(
            [("sale_order_id", "in", self.ids)],
            ["sale_order_id"],
            ["__count"],
        )
        counts = {order.id: count for order, count in grouped}
        for order in self:
            order.x_ticket_count = counts.get(order.id, 0)

    def action_view_support_tickets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Order Support Tickets"),
            "res_model": "custom.support.ticket",
            "view_mode": "list,kanban,form",
            "domain": [("sale_order_id", "=", self.id)],
            "context": {
                "default_sale_order_id": self.id,
                "default_partner_id": self.partner_id.id,
                "default_subject": _("Support for Order %s", self.name),
            },
        }

