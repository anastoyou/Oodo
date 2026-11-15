from odoo import api, fields, models


class CustomKnowledgeArticle(models.Model):
    _name = "custom.knowledge.article"
    _description = "Internal Knowledge Base & SOP Wiki"
    _inherit = ["mail.thread"]
    _order = "sequence, name"

    name = fields.Char(string="Article Title", required=True, tracking=True)
    sequence = fields.Integer(default=10)
    parent_id = fields.Many2one("custom.knowledge.article", string="Parent Article")
    category = fields.Selection(
        [
            ("sales_cod", "Sales, COD & RTO SOPs"),
            ("warehouse_qc", "Warehouse, Packing & QC"),
            ("finance_gst", "Finance, GST & Partner Accounting"),
            ("support_cx", "Customer Support & Exchange Scripts"),
            ("store_ops", "Retail POS & Store Operations"),
        ],
        default="sales_cod",
        required=True,
    )
    is_published = fields.Boolean(string="Visible to All Internal Staff", default=True)
    body = fields.Html(string="Article Content")
    author_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomAppointmentType(models.Model):
    _name = "custom.appointment.type"
    _description = "Online Appointment Type"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    duration_minutes = fields.Integer(default=30, required=True)
    location = fields.Char(default="Surat Studio / Video Call")
    staff_user_id = fields.Many2one("res.users", string="Assigned Specialist", domain="[('share', '=', False)]")
    description = fields.Text()


class CustomAppointmentBooking(models.Model):
    _name = "custom.appointment.booking"
    _description = "Customer Appointment Booking"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_datetime desc, id desc"

    name = fields.Char(string="Booking #", readonly=True, copy=False, default="New")
    appointment_type_id = fields.Many2one("custom.appointment.type", required=True, tracking=True)
    partner_id = fields.Many2one("res.partner", string="Customer")
    customer_name = fields.Char(required=True)
    customer_phone = fields.Char()
    customer_email = fields.Char()
    start_datetime = fields.Datetime(required=True, default=fields.Datetime.now, tracking=True)
    notes = fields.Text(string="Measurement / Styling Notes")
    state = fields.Selection(
        [("booked", "Booked"), ("confirmed", "Confirmed"), ("done", "Completed"), ("cancel", "Cancelled")],
        default="booked",
        tracking=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.appointment.booking") or "APT"
        return super().create(vals_list)

    def action_confirm(self):
        self.write({"state": "confirmed"})

    def action_done(self):
        self.write({"state": "done"})

    def action_cancel(self):
        self.write({"state": "cancel"})

