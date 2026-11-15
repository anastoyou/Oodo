from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from .account_enterprise import _post_balanced_journal_entry


class CustomSalaryStructure(models.Model):
    _name = "custom.salary.structure"
    _description = "Payroll Salary Structure"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    rule_ids = fields.One2many("custom.salary.rule", "structure_id", string="Salary Rules")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomSalaryRule(models.Model):
    _name = "custom.salary.rule"
    _description = "Payroll Salary Rule"
    _order = "sequence, id"

    structure_id = fields.Many2one("custom.salary.structure", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    code = fields.Char(required=True)
    rule_type = fields.Selection(
        [("earning", "Earning (+)"), ("deduction", "Deduction (-)")],
        default="earning",
        required=True,
    )
    compute_mode = fields.Selection(
        [("pct_gross", "% of Monthly CTC / Gross"), ("fixed", "Fixed Amount")],
        default="pct_gross",
        required=True,
    )
    percentage = fields.Float(string="Percentage (%)", default=0.0)
    fixed_amount = fields.Float(string="Fixed Amount", default=0.0)


class CustomHrPayslip(models.Model):
    _name = "custom.hr.payslip"
    _description = "Employee Payslip"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"

    name = fields.Char(string="Payslip #", readonly=True, copy=False, default="New")
    employee_id = fields.Many2one("hr.employee", required=True, tracking=True)
    structure_id = fields.Many2one("custom.salary.structure", required=True)
    date_from = fields.Date(required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    working_days = fields.Float(string="Paid Days", default=30.0, required=True)
    lop_days = fields.Float(string="LOP / Unpaid Days", default=0.0)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    monthly_gross = fields.Monetary(string="Base Monthly Gross", required=True, tracking=True)
    total_earnings = fields.Monetary(compute="_compute_totals", store=True)
    total_deductions = fields.Monetary(compute="_compute_totals", store=True)
    net_wage = fields.Monetary(string="Net Pay", compute="_compute_totals", store=True, tracking=True)
    state = fields.Selection(
        [("draft", "Draft"), ("verify", "Verified"), ("done", "Posted / Paid"), ("cancel", "Cancelled")],
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many("custom.hr.payslip.line", "payslip_id", string="Payslip Lines")
    journal_id = fields.Many2one("account.journal", domain="[('type', '=', 'general'), ('company_id', '=', company_id)]")
    expense_account_id = fields.Many2one("account.account", string="Salary Expense Account")
    payable_account_id = fields.Many2one("account.account", string="Salary Payable Account")
    move_id = fields.Many2one("account.move", string="Accounting Entry", readonly=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.depends("line_ids.amount", "line_ids.rule_type")
    def _compute_totals(self):
        for slip in self:
            earnings = sum(slip.line_ids.filtered(lambda l: l.rule_type == "earning").mapped("amount"))
            deductions = sum(slip.line_ids.filtered(lambda l: l.rule_type == "deduction").mapped("amount"))
            slip.total_earnings = earnings
            slip.total_deductions = deductions
            slip.net_wage = max(0.0, earnings - deductions)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.hr.payslip") or "SLIP"
        return super().create(vals_list)

    def action_compute_sheet(self):
        for slip in self:
            if slip.working_days <= 0:
                raise UserError(_("Paid Days must be greater than zero."))
            proration = max(0.0, (slip.working_days - slip.lop_days) / slip.working_days)
            effective_gross = slip.monthly_gross * proration
            slip.line_ids.unlink()
            lines = []
            for rule in slip.structure_id.rule_ids:
                amt = (effective_gross * rule.percentage / 100.0) if rule.compute_mode == "pct_gross" else rule.fixed_amount
                lines.append(Command.create({
                    "sequence": rule.sequence,
                    "name": rule.name,
                    "code": rule.code,
                    "rule_type": rule.rule_type,
                    "amount": round(amt, 2),
                }))
            slip.line_ids = lines
            slip.state = "verify"

    def action_confirm_and_post(self):
        for slip in self:
            if not slip.line_ids:
                slip.action_compute_sheet()
            if slip.journal_id and slip.expense_account_id and slip.payable_account_id and not slip.move_id and slip.net_wage > 0:
                partner = slip.employee_id.work_contact_id
                move = _post_balanced_journal_entry(
                    self.env,
                    slip.journal_id,
                    slip.date_to,
                    f"{slip.name} ({slip.employee_id.name})",
                    slip.expense_account_id,
                    slip.payable_account_id,
                    slip.net_wage,
                    f"Payroll Accrual: {slip.employee_id.name}",
                    partner=partner,
                )
                slip.move_id = move.id
            slip.state = "done"

    def action_cancel(self):
        self.write({"state": "cancel"})


class CustomHrPayslipLine(models.Model):
    _name = "custom.hr.payslip.line"
    _description = "Payslip Computation Line"
    _order = "sequence, id"

    payslip_id = fields.Many2one("custom.hr.payslip", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    code = fields.Char(required=True)
    rule_type = fields.Selection([("earning", "Earning"), ("deduction", "Deduction")], required=True)
    currency_id = fields.Many2one(related="payslip_id.currency_id", readonly=True)
    amount = fields.Monetary(required=True)


class CustomHrAppraisal(models.Model):
    _name = "custom.hr.appraisal"
    _description = "Employee Performance Appraisal"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "review_date desc, id desc"

    name = fields.Char(string="Appraisal Title", required=True, tracking=True)
    employee_id = fields.Many2one("hr.employee", required=True, tracking=True)
    manager_id = fields.Many2one("hr.employee", string="Reviewer / Manager")
    review_date = fields.Date(required=True, default=fields.Date.context_today)
    next_review_date = fields.Date()
    state = fields.Selection(
        [("new", "Scheduled"), ("pending", "Self & Manager Review"), ("done", "Completed"), ("cancel", "Cancelled")],
        default="new",
        tracking=True,
    )
    overall_rating = fields.Selection(
        [("1", "1 - Needs Improvement"), ("2", "2 - Meets Expectations"), ("3", "3 - Exceeds Expectations"), ("4", "4 - Outstanding")],
        default="2",
        tracking=True,
    )
    self_assessment = fields.Text(string="Employee Self-Review")
    manager_feedback = fields.Text(string="Manager Assessment & Increment Notes")
    goal_ids = fields.One2many("custom.hr.appraisal.goal", "appraisal_id", string="KPI Goals")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    def action_start_review(self):
        self.write({"state": "pending"})

    def action_complete(self):
        self.write({"state": "done"})


class CustomHrAppraisalGoal(models.Model):
    _name = "custom.hr.appraisal.goal"
    _description = "Employee Appraisal Goal"
    _order = "id asc"

    appraisal_id = fields.Many2one("custom.hr.appraisal", required=True, ondelete="cascade")
    name = fields.Char(string="Goal / KRA", required=True)
    target_metric = fields.Char(string="Target")
    progress_pct = fields.Float(string="Completion %", default=0.0)
    notes = fields.Char()


class CustomHrReferral(models.Model):
    _name = "custom.hr.referral"
    _description = "Employee Job Referral & Bonus Tracker"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(string="Candidate Name", required=True, tracking=True)
    referrer_id = fields.Many2one("hr.employee", string="Referred By", required=True, tracking=True)
    job_role = fields.Char(string="Target Role / Position", required=True)
    candidate_phone = fields.Char()
    candidate_email = fields.Char()
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    bonus_amount = fields.Monetary(string="Referral Bonus", default=2000.0)
    stage = fields.Selection(
        [("referred", "Referred"), ("interview", "Interviewing"), ("hired", "Hired"), ("paid", "Bonus Paid")],
        default="referred",
        tracking=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    def action_mark_interview(self):
        self.write({"stage": "interview"})

    def action_mark_hired(self):
        self.write({"stage": "hired"})

    def action_mark_paid(self):
        self.write({"stage": "paid"})

