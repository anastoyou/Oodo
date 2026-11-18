from datetime import timedelta
from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


PNL_ACCOUNT_TYPES = (
    "income",
    "income_other",
    "expense_direct_cost",
    "expense",
    "expense_other",
    "expense_depreciation",
)


class CustomFiscalYear(models.Model):
    _name = "custom.fiscal.year"
    _description = "Accounting Fiscal Year"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"

    name = fields.Char(required=True, tracking=True)
    date_from = fields.Date(string="Start Date", required=True, tracking=True)
    date_to = fields.Date(string="End Date", required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    state = fields.Selection(
        [("open", "Open"), ("closed", "Closed")],
        default="open",
        required=True,
        tracking=True,
    )
    retained_earnings_account_id = fields.Many2one(
        "account.account",
        string="Retained Earnings Account",
        domain="[('account_type', 'in', ('equity', 'equity_retained', 'equity_unaffected'))]",
    )
    closing_journal_id = fields.Many2one(
        "account.journal",
        string="Closing Journal",
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
    closing_move_id = fields.Many2one("account.move", string="Year-End Closing Entry", readonly=True, copy=False)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    net_profit = fields.Monetary(string="Fiscal Year Net P&L", compute="_compute_net_profit")

    @api.constrains("date_from", "date_to", "company_id")
    def _check_dates(self):
        for fy in self:
            if fy.date_to < fy.date_from:
                raise ValidationError(_("End Date must be on or after Start Date."))
            overlap = self.search([
                ("id", "!=", fy.id),
                ("company_id", "=", fy.company_id.id),
                ("date_from", "<=", fy.date_to),
                ("date_to", ">=", fy.date_from),
            ], limit=1)
            if overlap:
                raise ValidationError(_("Fiscal Year %s overlaps with %s.") % (fy.name, overlap.name))

    def _compute_net_profit(self):
        MoveLine = self.env["account.move.line"]
        for fy in self:
            if not (fy.date_from and fy.date_to):
                fy.net_profit = 0.0
                continue
            rows = MoveLine._read_group([
                ("company_id", "=", fy.company_id.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", fy.date_from),
                ("date", "<=", fy.date_to),
                ("account_id.account_type", "in", PNL_ACCOUNT_TYPES),
            ], [], ["balance:sum"])
            bal = rows[0][0] if rows and rows[0] else 0.0
            fy.net_profit = -bal

    def action_close_fiscal_year(self):
        """Create Year-End P&L Transfer Entry to Retained Earnings and optionally lock the period."""
        self.ensure_one()
        if self.state == "closed":
            raise UserError(_("Fiscal Year %s is already closed.") % self.name)
        if not self.closing_journal_id:
            self.closing_journal_id = self.env["account.journal"].search([
                ("company_id", "=", self.company_id.id),
                ("type", "=", "general"),
            ], limit=1)
        if not self.retained_earnings_account_id:
            self.retained_earnings_account_id = self.env["account.account"].search([
                ("company_ids", "in", self.company_id.id),
                ("account_type", "in", ("equity_retained", "equity_unaffected", "equity")),
            ], limit=1)
        if not (self.closing_journal_id and self.retained_earnings_account_id):
            raise UserError(_("Configure both a Closing Journal and Retained Earnings Account first."))

        if not self.closing_move_id:
            MoveLine = self.env["account.move.line"]
            grouped = MoveLine._read_group([
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("account_id.account_type", "in", PNL_ACCOUNT_TYPES),
            ], ["account_id"], ["balance:sum"])

            line_cmds = []
            net_balance = 0.0
            for account, balance in grouped:
                if not account or round(balance, 2) == 0.0:
                    continue
                net_balance += balance
                # Zero out each P&L account: if credit balance (<0), debit it; if debit balance (>0), credit it.
                line_cmds.append(Command.create({
                    "name": f"Year-End Close {self.name}: {account.name}",
                    "account_id": account.id,
                    "debit": round(-balance, 2) if balance < 0 else 0.0,
                    "credit": round(balance, 2) if balance > 0 else 0.0,
                }))
            if line_cmds:
                line_cmds.append(Command.create({
                    "name": f"Year-End Net P&L Transfer ({self.name})",
                    "account_id": self.retained_earnings_account_id.id,
                    "debit": round(net_balance, 2) if net_balance > 0 else 0.0,
                    "credit": round(-net_balance, 2) if net_balance < 0 else 0.0,
                }))
                move = self.env["account.move"].create({
                    "move_type": "entry",
                    "journal_id": self.closing_journal_id.id,
                    "date": self.date_to,
                    "ref": f"Closing {self.name}",
                    "company_id": self.company_id.id,
                    "line_ids": line_cmds,
                })
                move.action_post()
                self.closing_move_id = move.id

        self.company_id.sudo().write({"fiscalyear_lock_date": self.date_to})
        self.state = "closed"
        self.message_post(body=_("Fiscal Year %s closed and Period Lock Date updated to %s.") % (self.name, self.date_to))

    def action_reopen(self):
        self.write({"state": "open"})


class CustomAutoTransfer(models.Model):
    _name = "custom.auto.transfer"
    _description = "Automatic Account Transfer Rule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(required=True, tracking=True)
    date_start = fields.Date(required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_stop = fields.Date(required=True, default=lambda self: fields.Date.today() + relativedelta(years=1))
    frequency = fields.Selection(
        [("month", "Monthly"), ("quarter", "Quarterly"), ("year", "Yearly")],
        default="month",
        required=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
    origin_account_ids = fields.Many2many(
        "account.account",
        string="Origin Accounts",
        required=True,
    )
    line_ids = fields.One2many("custom.auto.transfer.line", "transfer_id", string="Destination Rules")
    move_ids = fields.Many2many("account.move", string="Generated Transfers", readonly=True, copy=False)
    move_count = fields.Integer(compute="_compute_move_count")
    state = fields.Selection(
        [("draft", "Draft"), ("in_progress", "Running"), ("disabled", "Disabled")],
        default="draft",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)

    @api.constrains("line_ids")
    def _check_percentages(self):
        for rec in self:
            if rec.state == "in_progress" and rec.line_ids:
                tot = round(sum(rec.line_ids.mapped("percent")), 2)
                if tot != 100.0:
                    raise ValidationError(_("Destination percentages must sum to 100%% (currently %.2f%%).") % tot)

    def action_activate(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Add at least one destination rule before activating."))
            tot = round(sum(rec.line_ids.mapped("percent")), 2)
            if tot != 100.0:
                raise UserError(_("Destination percentages must sum to 100%% (currently %.2f%%).") % tot)
            rec.state = "in_progress"

    def action_disable(self):
        self.write({"state": "disabled"})

    def action_compute_transfer(self):
        """Post an automatic transfer entry for the current period's origin account balance."""
        MoveLine = self.env["account.move.line"]
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.origin_account_ids or not rec.line_ids:
                raise UserError(_("Origin accounts and destination lines are required."))
            period_start = max(rec.date_start, today.replace(day=1))
            period_end = min(rec.date_stop, today)
            if period_end < period_start:
                period_start = rec.date_start
                period_end = rec.date_stop

            grouped = MoveLine._read_group([
                ("company_id", "=", rec.company_id.id),
                ("parent_state", "=", "posted"),
                ("account_id", "in", rec.origin_account_ids.ids),
                ("date", ">=", period_start),
                ("date", "<=", period_end),
                ("move_id", "not in", rec.move_ids.ids),
            ], ["account_id"], ["balance:sum"])

            line_cmds = []
            total_transfer = 0.0
            for acc, bal in grouped:
                if not acc or round(bal, 2) == 0.0:
                    continue
                total_transfer += bal
                # Clear origin account for this period
                line_cmds.append(Command.create({
                    "name": f"Auto-Transfer Out: {acc.name}",
                    "account_id": acc.id,
                    "debit": round(-bal, 2) if bal < 0 else 0.0,
                    "credit": round(bal, 2) if bal > 0 else 0.0,
                }))

            if not line_cmds or round(total_transfer, 2) == 0.0:
                raise UserError(_("No un-transferred balance found in origin accounts for %s → %s.") % (period_start, period_end))

            allocated = 0.0
            dest_lines = rec.line_ids
            for idx, dline in enumerate(dest_lines):
                if idx == len(dest_lines) - 1:
                    amt = round(total_transfer - allocated, 2)
                else:
                    amt = round(total_transfer * (dline.percent / 100.0), 2)
                    allocated += amt
                vals = {
                    "name": f"Auto-Transfer In ({dline.percent:.1f}%): {rec.name}",
                    "account_id": dline.account_id.id,
                    "debit": amt if amt > 0 else 0.0,
                    "credit": -amt if amt < 0 else 0.0,
                }
                if dline.analytic_account_id:
                    vals["analytic_distribution"] = {str(dline.analytic_account_id.id): 100.0}
                line_cmds.append(Command.create(vals))

            move = self.env["account.move"].create({
                "move_type": "entry",
                "journal_id": rec.journal_id.id,
                "date": period_end,
                "ref": f"Auto Transfer: {rec.name}",
                "company_id": rec.company_id.id,
                "line_ids": line_cmds,
            })
            move.action_post()
            rec.move_ids = [Command.link(move.id)]

    def action_view_moves(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Generated Transfer Entries"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.move_ids.ids)],
        }

    @api.model
    def _cron_execute_auto_transfers(self):
        today = fields.Date.context_today(self)
        rules = self.search([
            ("state", "=", "in_progress"),
            ("date_start", "<=", today),
            ("date_stop", ">=", today),
        ])
        for rule in rules:
            try:
                rule.action_compute_transfer()
            except UserError:
                continue


class CustomAutoTransferLine(models.Model):
    _name = "custom.auto.transfer.line"
    _description = "Automatic Transfer Destination Line"
    _order = "id asc"

    transfer_id = fields.Many2one("custom.auto.transfer", required=True, ondelete="cascade")
    account_id = fields.Many2one("account.account", string="Destination Account", required=True)
    analytic_account_id = fields.Many2one("account.analytic.account", string="Analytic Account")
    percent = fields.Float(string="Allocation (%)", required=True, default=100.0)


class CustomDisallowedExpenseCategory(models.Model):
    _name = "custom.disallowed.expense.category"
    _description = "Disallowed Expense Category"
    _order = "code, name"

    code = fields.Char(required=True)
    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    rate_ids = fields.One2many("custom.disallowed.expense.rate", "category_id", string="Non-Deductible Rates")
    account_ids = fields.One2many("account.account", "disallowed_expense_category_id", string="Linked Accounts")

    def _get_rate_for_date(self, target_date):
        self.ensure_one()
        rates = self.rate_ids.filtered(lambda r: r.date_from <= target_date).sorted("date_from", reverse=True)
        return rates[0].rate if rates else 0.0


class CustomDisallowedExpenseRate(models.Model):
    _name = "custom.disallowed.expense.rate"
    _description = "Disallowed Expense Rate"
    _order = "date_from desc"

    category_id = fields.Many2one("custom.disallowed.expense.category", required=True, ondelete="cascade")
    date_from = fields.Date(string="Effective From", required=True, default=fields.Date.context_today)
    rate = fields.Float(string="Disallowed (%)", required=True, default=50.0)

    @api.constrains("rate")
    def _check_rate(self):
        for r in self:
            if r.rate < 0 or r.rate > 100:
                raise ValidationError(_("Disallowed percentage must be between 0 and 100."))


class AccountAccountDisallowedExt(models.Model):
    _inherit = "account.account"

    disallowed_expense_category_id = fields.Many2one(
        "custom.disallowed.expense.category",
        string="Disallowed Expenses Category",
        help="Non-tax-deductible expense percentage rule applied to this account.",
    )


class CustomDisallowedExpenseReport(models.TransientModel):
    _name = "custom.disallowed.expense.report"
    _description = "Disallowed Expenses Analysis"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    date_from = fields.Date(required=True, default=lambda self: fields.Date.today().replace(month=4, day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    line_ids = fields.One2many("custom.disallowed.expense.report.line", "report_id")
    total_book_expense = fields.Monetary(readonly=True)
    total_disallowed = fields.Monetary(readonly=True)
    total_deductible = fields.Monetary(readonly=True)

    @api.model
    def action_open_disallowed_report(self):
        wiz = self.create({"company_id": self.env.company.id})
        wiz.action_compute()
        return {
            "type": "ir.actions.act_window",
            "name": _("Disallowed Expenses Report"),
            "res_model": "custom.disallowed.expense.report",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        accounts = self.env["account.account"].search([("disallowed_expense_category_id", "!=", False)])
        MoveLine = self.env["account.move.line"]
        cmds = []
        tot_book = tot_dis = 0.0
        for acc in accounts:
            cat = acc.disallowed_expense_category_id
            rate = cat._get_rate_for_date(self.date_to)
            rows = MoveLine._read_group([
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("account_id", "=", acc.id),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
            ], [], ["balance:sum"])
            book = rows[0][0] if rows and rows[0] else 0.0
            if round(book, 2) == 0.0:
                continue
            disallowed = round(book * (rate / 100.0), 2)
            tot_book += book
            tot_dis += disallowed
            cmds.append(Command.create({
                "category_id": cat.id,
                "account_id": acc.id,
                "disallowed_rate": rate,
                "book_amount": round(book, 2),
                "disallowed_amount": disallowed,
                "deductible_amount": round(book - disallowed, 2),
            }))
        self.write({
            "line_ids": cmds,
            "total_book_expense": round(tot_book, 2),
            "total_disallowed": round(tot_dis, 2),
            "total_deductible": round(tot_book - tot_dis, 2),
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Disallowed Expenses Report"),
            "res_model": "custom.disallowed.expense.report",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }


class CustomDisallowedExpenseReportLine(models.TransientModel):
    _name = "custom.disallowed.expense.report.line"
    _description = "Disallowed Expense Report Line"

    report_id = fields.Many2one("custom.disallowed.expense.report", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="report_id.currency_id", readonly=True)
    category_id = fields.Many2one("custom.disallowed.expense.category", readonly=True)
    account_id = fields.Many2one("account.account", readonly=True)
    disallowed_rate = fields.Float(string="Disallowed %", readonly=True)
    book_amount = fields.Monetary(string="Book Expense", readonly=True)
    disallowed_amount = fields.Monetary(string="Non-Deductible", readonly=True)
    deductible_amount = fields.Monetary(string="Tax Deductible", readonly=True)
