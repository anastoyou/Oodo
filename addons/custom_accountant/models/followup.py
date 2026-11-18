from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CustomFollowupLevel(models.Model):
    _name = "custom.followup.level"
    _description = "Customer Payment Follow-up Level"
    _order = "delay asc, sequence asc, id asc"

    name = fields.Char(string="Follow-up Action Name", required=True, translate=True)
    sequence = fields.Integer(default=10)
    delay = fields.Integer(
        string="Due Days",
        required=True,
        default=15,
        help="Number of days overdue before this follow-up level is triggered.",
    )
    send_email = fields.Boolean(string="Send Email", default=True)
    auto_execute = fields.Boolean(string="Automatic", default=False)
    block_sales = fields.Boolean(string="Warn on New Sales", default=False)
    note = fields.Text(
        string="Reminder Message",
        translate=True,
        default="Dear Customer,\n\nOur records indicate that the following invoice(s) are past due. Kindly arrange payment at your earliest convenience.",
    )
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    @api.constrains("delay")
    def _check_delay(self):
        for rec in self:
            if rec.delay < 0:
                raise ValidationError(_("Due days must be zero or positive."))


class ResPartnerFollowup(models.Model):
    _inherit = "res.partner"

    followup_line_ids = fields.One2many(
        "account.move.line",
        compute="_compute_followup_lines",
        string="Unreconciled Receivable Items",
    )
    total_due = fields.Monetary(
        string="Total Receivable Due",
        compute="_compute_followup_summary",
        currency_field="currency_id",
    )
    total_overdue = fields.Monetary(
        string="Total Overdue",
        compute="_compute_followup_summary",
        currency_field="currency_id",
    )
    followup_status = fields.Selection(
        [
            ("in_need_of_action", "In Need of Action"),
            ("with_overdue_invoices", "With Overdue Invoices"),
            ("no_action_needed", "No Action Needed"),
        ],
        string="Follow-up Status",
        compute="_compute_followup_summary",
        search="_search_followup_status",
    )
    followup_level_id = fields.Many2one(
        "custom.followup.level",
        string="Follow-up Level",
        compute="_compute_followup_summary",
    )
    followup_next_action_date = fields.Date(
        string="Next Follow-up Reminder",
        company_dependent=True,
        copy=False,
    )
    followup_reminder_type = fields.Selection(
        [("automatic", "Automatic"), ("manual", "Manual")],
        string="Follow-up Reminders",
        default="automatic",
        company_dependent=True,
    )

    def _compute_followup_lines(self):
        MoveLine = self.env["account.move.line"]
        for partner in self:
            partner.followup_line_ids = MoveLine.search([
                ("partner_id", "=", partner.commercial_partner_id.id),
                ("company_id", "=", self.env.company.id),
                ("parent_state", "=", "posted"),
                ("account_id.account_type", "=", "asset_receivable"),
                ("reconciled", "=", False),
                ("amount_residual", ">", 0),
            ], order="date_maturity asc, date asc")

    @api.depends("followup_next_action_date")
    def _compute_followup_summary(self):
        today = fields.Date.context_today(self)
        levels = self.env["custom.followup.level"].search([], order="delay desc")
        MoveLine = self.env["account.move.line"]
        all_lines = MoveLine.search([
            ("partner_id", "in", self.mapped("commercial_partner_id").ids),
            ("company_id", "=", self.env.company.id),
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("reconciled", "=", False),
            ("amount_residual", ">", 0),
        ])
        by_partner = {}
        for line in all_lines:
            by_partner.setdefault(line.partner_id.id, []).append(line)

        for partner in self:
            p_lines = by_partner.get(partner.commercial_partner_id.id, [])
            due = sum(l.amount_residual for l in p_lines)
            overdue_lines = [l for l in p_lines if (l.date_maturity or l.date) < today]
            overdue = sum(l.amount_residual for l in overdue_lines)
            max_days = max(((today - (l.date_maturity or l.date)).days for l in overdue_lines), default=-1)
            matched_level = False
            if max_days >= 0:
                for lvl in levels:
                    if max_days >= lvl.delay:
                        matched_level = lvl
                        break
            partner.total_due = due
            partner.total_overdue = overdue
            partner.followup_level_id = matched_level
            if overdue > 0:
                if not partner.followup_next_action_date or partner.followup_next_action_date <= today:
                    partner.followup_status = "in_need_of_action"
                else:
                    partner.followup_status = "with_overdue_invoices"
            else:
                partner.followup_status = "no_action_needed"

    def _search_followup_status(self, operator, value):
        if operator not in ("=", "!="):
            return []
        today = fields.Date.context_today(self)
        overdue_lines = self.env["account.move.line"].search([
            ("company_id", "=", self.env.company.id),
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("reconciled", "=", False),
            ("amount_residual", ">", 0),
            ("date_maturity", "<", today),
        ])
        overdue_partner_ids = overdue_lines.mapped("partner_id").ids
        matching = []
        for partner in self.browse(overdue_partner_ids):
            if partner.followup_status == value:
                matching.append(partner.id)
        if operator == "=":
            if value == "no_action_needed":
                return [("id", "not in", overdue_partner_ids)]
            return [("id", "in", matching)]
        return [("id", "not in", matching)]

    def action_send_followup_email(self):
        self.ensure_one()
        if self.total_due <= 0:
            raise UserError(_("Partner %s has no open receivable balance.") % self.display_name)
        lvl = self.followup_level_id
        note = (lvl.note if lvl else "") or _("Friendly reminder: please review your overdue statement.")
        body = _(
            "<p><strong>Payment Follow-up (%s)</strong></p>"
            "<p>%s</p>"
            "<p>Total Due: <strong>%s %.2f</strong> | Overdue: <strong>%s %.2f</strong></p>"
        ) % (
            lvl.name if lvl else _("Standard Reminder"),
            note.replace("\n", "<br/>"),
            self.company_id.currency_id.symbol or "",
            self.total_due,
            self.company_id.currency_id.symbol or "",
            self.total_overdue,
        )
        if self.email:
            self.env["mail.mail"].sudo().create({
                "subject": _("Payment Reminder: %s") % self.company_id.name,
                "email_to": self.email,
                "body_html": body,
                "auto_delete": True,
            }).send()
        self.message_post(body=body, subject=_("Follow-up Reminder Sent"))
        self.followup_next_action_date = fields.Date.context_today(self) + timedelta(days=7)

    def action_followup_done(self):
        for partner in self:
            partner.followup_next_action_date = fields.Date.context_today(self) + timedelta(days=15)
            partner.message_post(body=_("Follow-up marked done; next reminder scheduled for %s.") % partner.followup_next_action_date)

    def action_print_followup_statement(self):
        self.ensure_one()
        return self.env.ref("custom_accountant.action_report_followup_statement").report_action(self)

    @api.model
    def _cron_process_followups(self):
        today = fields.Date.context_today(self)
        overdue_lines = self.env["account.move.line"].search([
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("reconciled", "=", False),
            ("amount_residual", ">", 0),
            ("date_maturity", "<", today),
        ])
        for partner in overdue_lines.mapped("partner_id"):
            if (
                partner.followup_reminder_type == "automatic"
                and partner.followup_status == "in_need_of_action"
                and partner.followup_level_id.auto_execute
                and partner.email
            ):
                partner.action_send_followup_email()
