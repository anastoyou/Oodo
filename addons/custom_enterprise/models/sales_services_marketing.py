import uuid
from datetime import timedelta
from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class CustomSignTemplate(models.Model):
    _name = "custom.sign.template"
    _description = "e-Signature Document Template"
    _order = "name"

    name = fields.Char(required=True)
    document_pdf = fields.Binary(string="Template PDF", attachment=True)
    document_filename = fields.Char()
    agreement_body = fields.Html(string="Online Agreement / Terms Body")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomSignRequest(models.Model):
    _name = "custom.sign.request"
    _description = "e-Signature Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Reference", readonly=True, copy=False, default="New")
    subject = fields.Char(required=True, tracking=True)
    template_id = fields.Many2one("custom.sign.template", string="Template")
    document_pdf = fields.Binary(string="PDF Document", attachment=True)
    document_filename = fields.Char()
    agreement_body = fields.Html(string="Agreement Text")
    sale_order_id = fields.Many2one("sale.order", string="Related Order")
    state = fields.Selection(
        [("draft", "Draft"), ("sent", "Waiting Signatures"), ("signed", "Fully Signed"), ("cancel", "Cancelled")],
        default="draft",
        tracking=True,
    )
    signer_ids = fields.One2many("custom.sign.signer", "request_id", string="Signers")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.onchange("template_id")
    def _onchange_template_id(self):
        for rec in self:
            if rec.template_id:
                rec.document_pdf = rec.template_id.document_pdf
                rec.document_filename = rec.template_id.document_filename
                rec.agreement_body = rec.template_id.agreement_body

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.sign.request") or "SIGN"
        return super().create(vals_list)

    def action_send(self):
        for req in self:
            if not req.signer_ids:
                raise UserError(_("Add at least one signer before sending."))
            for signer in req.signer_ids:
                if not signer.access_token:
                    signer.access_token = uuid.uuid4().hex
                signer.state = "sent"
            req.state = "sent"
            links = ", ".join(s.sign_url for s in req.signer_ids if s.sign_url)
            req.message_post(body=_("Signature request activated. Signing link(s): %s") % links)

    def action_cancel(self):
        self.write({"state": "cancel"})


class CustomSignSigner(models.Model):
    _name = "custom.sign.signer"
    _description = "e-Signature Signer"
    _order = "id asc"

    request_id = fields.Many2one("custom.sign.request", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Signer", required=True)
    email = fields.Char(related="partner_id.email", readonly=False)
    role = fields.Char(default="Authorized Signatory")
    access_token = fields.Char(readonly=True, copy=False)
    sign_url = fields.Char(string="Signing Link", compute="_compute_sign_url")
    state = fields.Selection([("draft", "Draft"), ("sent", "Pending"), ("signed", "Signed")], default="draft", required=True)
    signed_name = fields.Char(string="Typed Signature", readonly=True)
    signature_image = fields.Binary(string="Drawn Signature", readonly=True, attachment=True)
    signed_on = fields.Datetime(readonly=True)
    signed_ip = fields.Char(string="Signer IP", readonly=True)

    @api.depends("access_token")
    def _compute_sign_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_str("web.base.url", "")
        for signer in self:
            signer.sign_url = f"{base_url}/my/sign/{signer.access_token}" if signer.access_token else False


class CustomSubscriptionPlan(models.Model):
    _name = "custom.subscription.plan"
    _description = "Subscription Billing Plan"
    _order = "name"

    name = fields.Char(required=True)
    billing_period = fields.Selection(
        [("month", "Monthly"), ("quarter", "Quarterly"), ("year", "Yearly")],
        default="month",
        required=True,
    )
    interval_count = fields.Integer(default=1, required=True)
    auto_post_invoice = fields.Boolean(default=False)


class CustomSubscription(models.Model):
    _name = "custom.subscription"
    _description = "Recurring Subscription Contract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "next_invoice_date asc, id desc"

    name = fields.Char(string="Subscription #", readonly=True, copy=False, default="New")
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, tracking=True)
    plan_id = fields.Many2one("custom.subscription.plan", required=True, tracking=True)
    start_date = fields.Date(required=True, default=fields.Date.context_today)
    next_invoice_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    state = fields.Selection(
        [("draft", "Quotation"), ("active", "In Progress"), ("paused", "Paused"), ("closed", "Churned / Closed")],
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many("custom.subscription.line", "subscription_id", string="Recurring Items")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    recurring_total = fields.Monetary(string="Period Amount", compute="_compute_mrr", store=True)
    mrr_amount = fields.Monetary(string="MRR", compute="_compute_mrr", store=True)
    invoice_ids = fields.Many2many("account.move", string="Generated Invoices", copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.depends("line_ids.subtotal", "plan_id.billing_period", "plan_id.interval_count")
    def _compute_mrr(self):
        for sub in self:
            total = sum(sub.line_ids.mapped("subtotal"))
            sub.recurring_total = total
            months = 1
            if sub.plan_id:
                factor = {"month": 1, "quarter": 3, "year": 12}.get(sub.plan_id.billing_period, 1)
                months = max(1, factor * max(1, sub.plan_id.interval_count))
            sub.mrr_amount = round(total / months, 2)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.subscription") or "SUB"
        return super().create(vals_list)

    def action_activate(self):
        self.write({"state": "active"})

    def action_pause(self):
        self.write({"state": "paused"})

    def action_close(self):
        self.write({"state": "closed"})

    def _next_cycle_date(self, current_date):
        self.ensure_one()
        count = max(1, self.plan_id.interval_count)
        if self.plan_id.billing_period == "month":
            return current_date + relativedelta(months=count)
        if self.plan_id.billing_period == "quarter":
            return current_date + relativedelta(months=3 * count)
        return current_date + relativedelta(years=count)

    def action_generate_invoice(self):
        Move = self.env["account.move"]
        for sub in self:
            if not sub.line_ids:
                raise UserError(_("Add at least one subscription line before invoicing."))
            inv = Move.create({
                "move_type": "out_invoice",
                "partner_id": sub.partner_id.id,
                "invoice_origin": sub.name,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    Command.create({
                        "product_id": line.product_id.id,
                        "name": line.name or line.product_id.display_name,
                        "quantity": line.quantity,
                        "price_unit": line.price_unit,
                    })
                    for line in sub.line_ids
                ],
            })
            if sub.plan_id.auto_post_invoice:
                inv.action_post()
            sub.invoice_ids = [Command.link(inv.id)]
            sub.next_invoice_date = sub._next_cycle_date(sub.next_invoice_date or fields.Date.today())
            sub.message_post(body=_("Generated recurring invoice %s.") % inv.name)

    @api.model
    def _cron_generate_subscription_invoices(self):
        today = fields.Date.today()
        due = self.search([("state", "=", "active"), ("next_invoice_date", "<=", today)])
        for sub in due:
            if sub.line_ids:
                sub.action_generate_invoice()


class CustomSubscriptionLine(models.Model):
    _name = "custom.subscription.line"
    _description = "Subscription Recurring Line"

    subscription_id = fields.Many2one("custom.subscription", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True)
    name = fields.Char(string="Description")
    quantity = fields.Float(default=1.0, required=True)
    currency_id = fields.Many2one(related="subscription_id.currency_id", readonly=True)
    price_unit = fields.Monetary(required=True)
    subtotal = fields.Monetary(compute="_compute_subtotal", store=True)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.name = line.product_id.display_name
                line.price_unit = line.product_id.lst_price

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit


class CustomRentalOrder(models.Model):
    _name = "custom.rental.order"
    _description = "Occasion Wear & Gadget Rental Booking"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "pickup_date desc, id desc"

    name = fields.Char(string="Rental #", readonly=True, copy=False, default="New")
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, tracking=True)
    pickup_date = fields.Datetime(required=True, default=fields.Datetime.now)
    return_due_date = fields.Datetime(required=True, default=lambda self: fields.Datetime.now() + timedelta(days=3))
    actual_return_date = fields.Datetime(readonly=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    security_deposit = fields.Monetary(string="Security Deposit", default=0.0)
    late_fee_per_day = fields.Monetary(string="Late Fee / Day", default=250.0)
    late_fee_total = fields.Monetary(compute="_compute_totals", store=True)
    rental_subtotal = fields.Monetary(compute="_compute_totals", store=True)
    total_payable = fields.Monetary(compute="_compute_totals", store=True)
    state = fields.Selection(
        [("draft", "Draft"), ("reserved", "Reserved"), ("picked_up", "Picked Up"), ("returned", "Returned"), ("cancel", "Cancelled")],
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many("custom.rental.line", "rental_id", string="Rental Items")
    invoice_id = fields.Many2one("account.move", string="Rental Invoice", readonly=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.depends("line_ids.subtotal", "actual_return_date", "return_due_date", "late_fee_per_day")
    def _compute_totals(self):
        for rec in self:
            base_total = sum(rec.line_ids.mapped("subtotal"))
            late_fee = 0.0
            if rec.actual_return_date and rec.return_due_date and rec.actual_return_date > rec.return_due_date:
                overdue_days = (rec.actual_return_date.date() - rec.return_due_date.date()).days
                if overdue_days > 0:
                    late_fee = overdue_days * rec.late_fee_per_day
            rec.rental_subtotal = base_total
            rec.late_fee_total = late_fee
            rec.total_payable = base_total + late_fee

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.rental.order") or "RNT"
        return super().create(vals_list)

    def action_reserve(self):
        self.write({"state": "reserved"})

    def action_pickup(self):
        self.write({"state": "picked_up"})

    def action_return(self):
        self.write({"state": "returned", "actual_return_date": fields.Datetime.now()})

    def action_create_invoice(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Add at least one rental line first."))
        inv = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner_id.id,
            "invoice_origin": self.name,
            "invoice_line_ids": [
                Command.create({
                    "product_id": line.product_id.id,
                    "name": f"Rental: {line.product_id.display_name}",
                    "quantity": line.quantity,
                    "price_unit": line.rental_price,
                })
                for line in self.line_ids
            ],
        })
        self.invoice_id = inv.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": inv.id,
            "view_mode": "form",
        }


class CustomRentalLine(models.Model):
    _name = "custom.rental.line"
    _description = "Rental Booking Line"

    rental_id = fields.Many2one("custom.rental.order", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True)
    quantity = fields.Float(default=1.0, required=True)
    currency_id = fields.Many2one(related="rental_id.currency_id", readonly=True)
    rental_price = fields.Monetary(string="Rental Rate", required=True)
    subtotal = fields.Monetary(compute="_compute_subtotal", store=True)

    @api.depends("quantity", "rental_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.rental_price


class CustomMarketingCampaign(models.Model):
    _name = "custom.marketing.campaign"
    _description = "Marketing Automation Drip Campaign"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(required=True)
    model_name = fields.Selection(
        [("res.partner", "Customers / Contacts"), ("crm.lead", "CRM Leads"), ("sale.order", "Sales Orders")],
        default="res.partner",
        required=True,
    )
    domain_filter = fields.Char(string="Target Filter Domain", default="[]")
    state = fields.Selection([("draft", "Draft"), ("running", "Running"), ("stopped", "Stopped")], default="draft", tracking=True)
    step_ids = fields.One2many("custom.marketing.step", "campaign_id", string="Workflow Steps")
    trace_count = fields.Integer(compute="_compute_trace_count")

    def _compute_trace_count(self):
        Trace = self.env["custom.marketing.trace"]
        for camp in self:
            camp.trace_count = Trace.search_count([("campaign_id", "=", camp.id)])

    def action_start(self):
        self.write({"state": "running"})

    def action_stop(self):
        self.write({"state": "stopped"})

    def action_run_now(self):
        Trace = self.env["custom.marketing.trace"]
        for camp in self:
            domain = safe_eval(camp.domain_filter or "[]")
            records = self.env[camp.model_name].search(domain, limit=200)
            for step in camp.step_ids.sorted("sequence"):
                for rec in records:
                    already = Trace.search_count([
                        ("campaign_id", "=", camp.id),
                        ("step_id", "=", step.id),
                        ("res_id", "=", rec.id),
                    ])
                    if already:
                        continue
                    step._execute_on_record(rec)
                    Trace.create({
                        "campaign_id": camp.id,
                        "step_id": step.id,
                        "res_model": camp.model_name,
                        "res_id": rec.id,
                        "status": "done",
                    })

    @api.model
    def _cron_run_marketing_campaigns(self):
        self.search([("state", "=", "running")]).action_run_now()


class CustomMarketingStep(models.Model):
    _name = "custom.marketing.step"
    _description = "Marketing Automation Step"
    _order = "sequence, id"

    campaign_id = fields.Many2one("custom.marketing.campaign", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    action_type = fields.Selection(
        [("email", "Send Email Template"), ("activity", "Schedule Follow-Up Activity"), ("tag", "Add Contact Tag")],
        default="activity",
        required=True,
    )
    mail_template_id = fields.Many2one("mail.template", string="Email Template")
    activity_summary = fields.Char(default="Marketing Follow-Up")
    partner_tag_id = fields.Many2one("res.partner.category", string="Partner Tag")

    def _execute_on_record(self, rec):
        self.ensure_one()
        if self.action_type == "email" and self.mail_template_id:
            self.mail_template_id.send_mail(rec.id, force_send=False)
        elif self.action_type == "activity" and hasattr(rec, "activity_schedule"):
            rec.activity_schedule(summary=self.activity_summary or self.name)
        elif self.action_type == "tag" and self.partner_tag_id:
            partner = rec if rec._name == "res.partner" else getattr(rec, "partner_id", False)
            if partner:
                partner.write({"category_id": [Command.link(self.partner_tag_id.id)]})


class CustomMarketingTrace(models.Model):
    _name = "custom.marketing.trace"
    _description = "Marketing Execution Log"
    _order = "id desc"

    campaign_id = fields.Many2one("custom.marketing.campaign", required=True, ondelete="cascade")
    step_id = fields.Many2one("custom.marketing.step", required=True, ondelete="cascade")
    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    status = fields.Selection([("done", "Executed")], default="done")
    executed_at = fields.Datetime(default=fields.Datetime.now)


class CustomSocialPost(models.Model):
    _name = "custom.social.post"
    _description = "Multi-Brand Social Media Planner"
    _inherit = ["mail.thread"]
    _order = "scheduled_date desc, id desc"

    name = fields.Char(string="Campaign / Post Title", required=True)
    brand = fields.Selection(
        [("fairtag", "FAIRTAG"), ("zoira", "ZOIRA"), ("gadgets", "GADGETS")],
        default="fairtag",
        required=True,
    )
    channel = fields.Selection(
        [
            ("instagram", "Instagram Reels / Post"),
            ("facebook", "Facebook"),
            ("youtube", "YouTube Shorts"),
            ("whatsapp", "WhatsApp Status / Broadcast"),
            ("linkedin", "LinkedIn"),
        ],
        default="instagram",
        required=True,
    )
    scheduled_date = fields.Datetime(required=True, default=fields.Datetime.now)
    message_body = fields.Text(string="Caption / Copy", required=True)
    target_url = fields.Char(string="Landing / Product URL")
    utm_campaign = fields.Char(string="UTM Campaign Tag")
    state = fields.Selection(
        [("draft", "Draft"), ("scheduled", "Scheduled"), ("posted", "Published")],
        default="draft",
        tracking=True,
    )

    def action_schedule(self):
        self.write({"state": "scheduled"})

    def action_mark_posted(self):
        self.write({"state": "posted"})


class CustomFieldServiceTask(models.Model):
    _name = "custom.field.service.task"
    _description = "Field Service (Custom Tailoring / Store Maintenance / Gadget Visit)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "planned_date asc, id desc"

    name = fields.Char(string="Task #", readonly=True, copy=False, default="New")
    title = fields.Char(required=True, tracking=True)
    service_type = fields.Selection(
        [
            ("stitching_visit", "Custom Tailoring / Measurement Visit"),
            ("store_maintenance", "Retail Store / POS Maintenance"),
            ("gadget_install", "Gadget Setup / On-Site Repair"),
        ],
        default="stitching_visit",
        required=True,
    )
    partner_id = fields.Many2one("res.partner", string="Customer / Store Contact", required=True)
    technician_id = fields.Many2one("res.users", string="Assigned Technician / Tailor", domain="[('share', '=', False)]")
    planned_date = fields.Datetime(required=True, default=fields.Datetime.now)
    sale_order_id = fields.Many2one("sale.order", string="Related Order")
    worksheet_notes = fields.Text(string="Checklist & Measurement / Inspection Report")
    customer_signed_by = fields.Char(string="Customer Sign-Off Name")
    stage = fields.Selection(
        [("new", "Planned"), ("in_progress", "On Site"), ("done", "Completed"), ("cancel", "Cancelled")],
        default="new",
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.field.service.task") or "FSM"
        return super().create(vals_list)

    def action_start(self):
        self.write({"stage": "in_progress"})

    def action_done(self):
        self.write({"stage": "done"})


class CustomPlanningShift(models.Model):
    _name = "custom.planning.shift"
    _description = "Employee Roster & Shift Planning"
    _order = "start_datetime asc, id desc"

    name = fields.Char(string="Shift Title", required=True)
    employee_id = fields.Many2one("hr.employee", required=True)
    location_label = fields.Selection(
        [
            ("surat_hq", "Surat HQ Warehouse"),
            ("support_desk", "Support & COD Desk"),
            ("store_01", "Retail Store #1"),
            ("store_02", "Retail Store #2"),
        ],
        default="surat_hq",
        required=True,
    )
    role_name = fields.Char(string="Role / Duty", default="Warehouse Packing & QC")
    start_datetime = fields.Datetime(required=True, default=fields.Datetime.now)
    end_datetime = fields.Datetime(required=True, default=lambda self: fields.Datetime.now() + timedelta(hours=8))
    allocated_hours = fields.Float(compute="_compute_hours", store=True)
    state = fields.Selection([("draft", "Draft"), ("published", "Published")], default="draft")

    @api.depends("start_datetime", "end_datetime")
    def _compute_hours(self):
        for shift in self:
            if shift.start_datetime and shift.end_datetime and shift.end_datetime > shift.start_datetime:
                shift.allocated_hours = round((shift.end_datetime - shift.start_datetime).total_seconds() / 3600.0, 2)
            else:
                shift.allocated_hours = 0.0

    def action_publish(self):
        self.write({"state": "published"})
