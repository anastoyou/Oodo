import base64
import csv
import io
from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


def _post_balanced_journal_entry(env, journal, date, ref, debit_account, credit_account, amount, label, partner=False):
    """Create and post a two-line balanced journal entry."""
    if not journal:
        raise UserError(_("Please select a valid Journal before posting."))
    if amount <= 0:
        raise UserError(_("Amount to post must be strictly positive."))
    move = env["account.move"].create({
        "move_type": "entry",
        "journal_id": journal.id,
        "date": date,
        "ref": ref,
        "company_id": journal.company_id.id,
        "line_ids": [
            Command.create({
                "name": label,
                "account_id": debit_account.id,
                "partner_id": partner.id if partner else False,
                "debit": amount,
                "credit": 0.0,
            }),
            Command.create({
                "name": label,
                "account_id": credit_account.id,
                "partner_id": partner.id if partner else False,
                "debit": 0.0,
                "credit": amount,
            }),
        ],
    })
    move.action_post()
    return move


class CustomAssetCategory(models.Model):
    _name = "custom.asset.category"
    _description = "Fixed Asset Category"
    _order = "name"

    name = fields.Char(required=True)
    method = fields.Selection(
        [("linear", "Straight Line"), ("degressive", "Written Down Value (WDV)")],
        default="linear",
        required=True,
    )
    useful_life_months = fields.Integer(string="Useful Life (Months)", default=36, required=True)
    degressive_rate = fields.Float(string="Annual WDV Rate (%)", default=40.0)
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal",
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
    asset_account_id = fields.Many2one(
        "account.account",
        string="Fixed Asset Account",
        domain="[('company_ids', 'in', company_id)]",
    )
    depreciation_account_id = fields.Many2one(
        "account.account",
        string="Accumulated Depreciation Account",
        domain="[('company_ids', 'in', company_id)]",
    )
    expense_account_id = fields.Many2one(
        "account.account",
        string="Depreciation Expense Account",
        domain="[('company_ids', 'in', company_id)]",
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomAsset(models.Model):
    _name = "custom.asset"
    _description = "Fixed Asset & Depreciation Schedule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "acquisition_date desc, id desc"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string="Asset Code", readonly=True, copy=False, default="New")
    category_id = fields.Many2one("custom.asset.category", string="Category", required=True, tracking=True)
    acquisition_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    first_depreciation_date = fields.Date(required=True, default=fields.Date.context_today)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    original_value = fields.Monetary(string="Gross Value", required=True, tracking=True)
    salvage_value = fields.Monetary(string="Salvage / Residual Value", default=0.0)
    method = fields.Selection(related="category_id.method", readonly=False, store=True)
    useful_life_months = fields.Integer(string="Useful Life (Months)", default=36, required=True)
    degressive_rate = fields.Float(string="Annual WDV Rate (%)", default=40.0)
    journal_id = fields.Many2one("account.journal", string="Depreciation Journal")
    depreciation_account_id = fields.Many2one("account.account", string="Accumulated Depreciation Account")
    expense_account_id = fields.Many2one("account.account", string="Depreciation Expense Account")
    state = fields.Selection(
        [("draft", "Draft"), ("running", "Running"), ("closed", "Fully Depreciated / Disposed")],
        default="draft",
        required=True,
        tracking=True,
    )
    line_ids = fields.One2many("custom.asset.depreciation", "asset_id", string="Depreciation Schedule")
    depreciated_value = fields.Monetary(string="Posted Depreciation", compute="_compute_asset_values", store=True)
    book_value = fields.Monetary(string="Net Book Value", compute="_compute_asset_values", store=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.onchange("category_id")
    def _onchange_category_id(self):
        for asset in self:
            if not asset.category_id:
                continue
            cat = asset.category_id
            asset.method = cat.method
            asset.useful_life_months = cat.useful_life_months
            asset.degressive_rate = cat.degressive_rate
            asset.journal_id = cat.journal_id
            asset.depreciation_account_id = cat.depreciation_account_id
            asset.expense_account_id = cat.expense_account_id

    @api.depends("original_value", "line_ids.amount", "line_ids.move_id.state")
    def _compute_asset_values(self):
        for asset in self:
            posted = sum(
                line.amount for line in asset.line_ids if line.move_id and line.move_id.state == "posted"
            )
            asset.depreciated_value = posted
            asset.book_value = max(0.0, asset.original_value - posted)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("code") or vals["code"] == "New":
                vals["code"] = seq.next_by_code("custom.asset") or "AST"
        return super().create(vals_list)

    def action_compute_depreciation(self):
        """Rebuild unposted depreciation lines across the asset useful life."""
        for asset in self:
            if asset.useful_life_months <= 0:
                raise UserError(_("Useful life (months) must be positive."))
            depreciable = max(0.0, asset.original_value - asset.salvage_value)
            if depreciable <= 0:
                raise UserError(_("Depreciable amount (Gross - Salvage) must be greater than zero."))

            asset.line_ids.filtered(lambda l: not l.move_id).unlink()
            already_posted = sum(asset.line_ids.mapped("amount"))
            remaining = max(0.0, depreciable - already_posted)
            months_left = asset.useful_life_months - len(asset.line_ids)
            if months_left <= 0 or remaining <= 0:
                continue

            start_date = asset.first_depreciation_date or asset.acquisition_date
            offset = len(asset.line_ids)
            monthly_rate = (asset.degressive_rate / 100.0) / 12.0 if asset.method == "degressive" else 0.0
            vals = []
            running_nbv = remaining
            for idx in range(months_left):
                line_date = start_date + relativedelta(months=offset + idx)
                if idx == months_left - 1:
                    amt = round(running_nbv, 2)
                elif asset.method == "degressive" and monthly_rate > 0:
                    amt = round(min(running_nbv, running_nbv * monthly_rate), 2)
                else:
                    amt = round(remaining / months_left, 2)
                running_nbv = max(0.0, running_nbv - amt)
                vals.append({
                    "asset_id": asset.id,
                    "sequence": offset + idx + 1,
                    "depreciation_date": line_date,
                    "amount": amt,
                })
            self.env["custom.asset.depreciation"].create(vals)

    def action_validate(self):
        for asset in self:
            if not asset.line_ids:
                asset.action_compute_depreciation()
            asset.state = "running"

    def action_close(self):
        self.write({"state": "closed"})

    @api.model
    def _cron_post_due_depreciation(self):
        today = fields.Date.today()
        due_lines = self.env["custom.asset.depreciation"].search([
            ("asset_id.state", "=", "running"),
            ("move_id", "=", False),
            ("depreciation_date", "<=", today),
        ])
        for line in due_lines:
            if line.asset_id.journal_id and line.asset_id.expense_account_id and line.asset_id.depreciation_account_id:
                line.action_post_entry()


class CustomAssetDepreciation(models.Model):
    _name = "custom.asset.depreciation"
    _description = "Asset Depreciation Schedule Line"
    _order = "depreciation_date asc, sequence asc"

    asset_id = fields.Many2one("custom.asset", required=True, ondelete="cascade")
    sequence = fields.Integer(default=1)
    depreciation_date = fields.Date(required=True)
    currency_id = fields.Many2one(related="asset_id.currency_id", readonly=True)
    amount = fields.Monetary(required=True)
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True, copy=False)
    move_state = fields.Selection(related="move_id.state", readonly=True)

    def action_post_entry(self):
        for line in self:
            if line.move_id:
                continue
            asset = line.asset_id
            if not (asset.journal_id and asset.expense_account_id and asset.depreciation_account_id):
                raise UserError(_("Configure Journal, Depreciation Expense Account, and Accumulated Depreciation Account on asset %s.") % asset.name)
            move = _post_balanced_journal_entry(
                self.env,
                asset.journal_id,
                line.depreciation_date,
                f"{asset.code} - Depreciation #{line.sequence}",
                asset.expense_account_id,
                asset.depreciation_account_id,
                line.amount,
                f"Depreciation: {asset.name} ({line.depreciation_date})",
            )
            line.move_id = move.id


class CustomDeferredSchedule(models.Model):
    _name = "custom.deferred.schedule"
    _description = "Deferred Revenue & Prepaid Expense Schedule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"

    name = fields.Char(required=True, tracking=True)
    schedule_type = fields.Selection(
        [("expense", "Prepaid Expense Recognition"), ("revenue", "Deferred Revenue Recognition")],
        default="expense",
        required=True,
        tracking=True,
    )
    partner_id = fields.Many2one("res.partner", string="Partner")
    start_date = fields.Date(required=True, default=fields.Date.context_today)
    periods = fields.Integer(string="Recognition Months", default=12, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    total_amount = fields.Monetary(required=True)
    journal_id = fields.Many2one("account.journal", domain="[('type', '=', 'general'), ('company_id', '=', company_id)]")
    deferred_account_id = fields.Many2one("account.account", string="Prepaid / Deferred Account")
    recognition_account_id = fields.Many2one("account.account", string="Expense / Revenue Account")
    state = fields.Selection(
        [("draft", "Draft"), ("running", "Running"), ("done", "Completed")],
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many("custom.deferred.line", "schedule_id", string="Schedule Lines")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    def action_generate_lines(self):
        for rec in self:
            if rec.periods <= 0 or rec.total_amount <= 0:
                raise UserError(_("Total amount and periods must both be positive."))
            rec.line_ids.filtered(lambda l: not l.move_id).unlink()
            already_posted = sum(rec.line_ids.mapped("amount"))
            remaining = max(0.0, rec.total_amount - already_posted)
            periods_left = rec.periods - len(rec.line_ids)
            if periods_left <= 0 or remaining <= 0:
                continue
            vals = []
            accrued = 0.0
            for idx in range(periods_left):
                line_date = rec.start_date + relativedelta(months=len(rec.line_ids) + idx)
                amt = round(remaining - accrued, 2) if idx == periods_left - 1 else round(remaining / periods_left, 2)
                accrued += amt
                vals.append({
                    "schedule_id": rec.id,
                    "recognition_date": line_date,
                    "amount": amt,
                })
            self.env["custom.deferred.line"].create(vals)
            rec.state = "running"

    @api.model
    def _cron_post_due_deferred(self):
        today = fields.Date.today()
        due_lines = self.env["custom.deferred.line"].search([
            ("schedule_id.state", "=", "running"),
            ("move_id", "=", False),
            ("recognition_date", "<=", today),
        ])
        for line in due_lines:
            sched = line.schedule_id
            if sched.journal_id and sched.deferred_account_id and sched.recognition_account_id:
                line.action_post_entry()


class CustomDeferredLine(models.Model):
    _name = "custom.deferred.line"
    _description = "Deferred Recognition Line"
    _order = "recognition_date asc, id asc"

    schedule_id = fields.Many2one("custom.deferred.schedule", required=True, ondelete="cascade")
    recognition_date = fields.Date(required=True)
    currency_id = fields.Many2one(related="schedule_id.currency_id", readonly=True)
    amount = fields.Monetary(required=True)
    move_id = fields.Many2one("account.move", readonly=True, copy=False)

    def action_post_entry(self):
        for line in self:
            if line.move_id:
                continue
            sched = line.schedule_id
            if not (sched.journal_id and sched.deferred_account_id and sched.recognition_account_id):
                raise UserError(_("Configure Journal, Deferred Account, and Recognition Account on %s.") % sched.name)
            if sched.schedule_type == "expense":
                debit_acc, credit_acc = sched.recognition_account_id, sched.deferred_account_id
            else:
                debit_acc, credit_acc = sched.deferred_account_id, sched.recognition_account_id
            move = _post_balanced_journal_entry(
                self.env,
                sched.journal_id,
                line.recognition_date,
                f"{sched.name} ({line.recognition_date})",
                debit_acc,
                credit_acc,
                line.amount,
                f"{sched.name} recognition",
                partner=sched.partner_id,
            )
            line.move_id = move.id


class CustomAccountBudget(models.Model):
    _name = "custom.account.budget"
    _description = "Financial & Brand Budget"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"

    name = fields.Char(required=True, tracking=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("done", "Closed")],
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many("custom.account.budget.line", "budget_id", string="Budget Lines")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    total_planned = fields.Monetary(compute="_compute_total_planned", store=True)
    total_practical = fields.Monetary(compute="_compute_total_practical")

    @api.depends("line_ids.planned_amount")
    def _compute_total_planned(self):
        for budget in self:
            budget.total_planned = sum(budget.line_ids.mapped("planned_amount"))

    def _compute_total_practical(self):
        for budget in self:
            budget.total_practical = sum(budget.line_ids.mapped("practical_amount"))

    def action_confirm(self):
        self.write({"state": "confirmed"})

    def action_done(self):
        self.write({"state": "done"})


class CustomAccountBudgetLine(models.Model):
    _name = "custom.account.budget.line"
    _description = "Budget Line with Live Actuals"
    _order = "id asc"

    budget_id = fields.Many2one("custom.account.budget", required=True, ondelete="cascade")
    account_id = fields.Many2one("account.account", required=True)
    analytic_account_id = fields.Many2one("account.analytic.account", string="Brand / Channel Analytic")
    date_from = fields.Date(related="budget_id.date_from", store=True, readonly=False)
    date_to = fields.Date(related="budget_id.date_to", store=True, readonly=False)
    currency_id = fields.Many2one(related="budget_id.currency_id", readonly=True)
    planned_amount = fields.Monetary(string="Planned Amount", required=True)
    practical_amount = fields.Monetary(string="Actual Posted", compute="_compute_practical_amount")
    variance = fields.Monetary(string="Variance", compute="_compute_practical_amount")
    achievement_pct = fields.Float(string="Usage / Achievement %", compute="_compute_practical_amount")

    def _compute_practical_amount(self):
        MoveLine = self.env["account.move.line"]
        for line in self:
            if not (line.account_id and line.date_from and line.date_to):
                line.practical_amount = 0.0
                line.variance = line.planned_amount
                line.achievement_pct = 0.0
                continue
            domain = [
                ("account_id", "=", line.account_id.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", line.date_from),
                ("date", "<=", line.date_to),
            ]
            aml_rows = MoveLine.search(domain)
            if line.analytic_account_id:
                key = str(line.analytic_account_id.id)
                aml_rows = aml_rows.filtered(lambda r: r.analytic_distribution and key in r.analytic_distribution)
            actual = sum(aml_rows.mapped("balance"))
            line.practical_amount = actual
            line.variance = line.planned_amount - actual
            line.achievement_pct = (actual / line.planned_amount * 100.0) if line.planned_amount else 0.0


class CustomBankReconcileRule(models.Model):
    _name = "custom.bank.reconcile.rule"
    _description = "Automated Bank & UPI Reconciliation Rule"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    match_pattern = fields.Char(
        string="Label Contains (Keyword / Regex)",
        required=True,
        help="Case-insensitive substring matched against bank statement line label.",
    )
    transaction_sign = fields.Selection(
        [("both", "Debit & Credit"), ("positive", "Deposits / Credits Only"), ("negative", "Withdrawals / Debits Only")],
        default="both",
        required=True,
    )
    partner_id = fields.Many2one("res.partner", string="Force Partner")
    account_id = fields.Many2one("account.account", string="Counterpart Account")
    auto_match_open_invoices = fields.Boolean(
        string="Match Open Invoices/Bills by Exact Amount",
        default=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomBankImportWizard(models.TransientModel):
    _name = "custom.bank.import.wizard"
    _description = "CSV Bank & Razorpay/UPI Statement Import & Auto-Match"

    journal_id = fields.Many2one(
        "account.journal",
        string="Bank / Cash Journal",
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    csv_file = fields.Binary(string="CSV File (date,label,amount,reference)")
    csv_filename = fields.Char()
    csv_text = fields.Text(
        string="Or Paste CSV Rows",
        help="Format: YYYY-MM-DD,Description,Amount,Reference",
    )
    apply_rules = fields.Boolean(string="Apply Auto-Reconciliation Rules", default=True)
    result_summary = fields.Text(readonly=True)

    def action_import_and_match(self):
        self.ensure_one()
        raw_text = self.csv_text or ""
        if self.csv_file:
            raw_text = base64.b64decode(self.csv_file).decode("utf-8-sig", errors="replace")
        if not raw_text.strip():
            raise UserError(_("Upload a CSV file or paste CSV rows first."))

        reader = csv.reader(io.StringIO(raw_text.strip()))
        rules = self.env["custom.bank.reconcile.rule"].search([("active", "=", True)], order="sequence, id")
        created_lines = self.env["account.bank.statement.line"]
        matched_rules = 0

        for idx, row in enumerate(reader):
            if not row or len(row) < 3:
                continue
            if idx == 0 and row[0].strip().lower() in ("date", "txn_date", "transaction_date"):
                continue
            txn_date = row[0].strip()
            label = row[1].strip()
            amount = float(row[2].strip().replace(",", ""))
            ref = row[3].strip() if len(row) > 3 else ""

            matched_partner = False
            matched_invoice_note = ""
            if self.apply_rules:
                for rule in rules:
                    if rule.transaction_sign == "positive" and amount <= 0:
                        continue
                    if rule.transaction_sign == "negative" and amount >= 0:
                        continue
                    if rule.match_pattern.lower() in f"{label} {ref}".lower():
                        matched_partner = rule.partner_id
                        matched_rules += 1
                        break

                if not matched_partner or any(r.auto_match_open_invoices for r in rules):
                    move_type = "out_invoice" if amount > 0 else "in_invoice"
                    inv_domain = [
                        ("move_type", "=", move_type),
                        ("state", "=", "posted"),
                        ("payment_state", "in", ("not_paid", "partial")),
                        ("amount_residual", "=", abs(amount)),
                    ]
                    if matched_partner:
                        inv_domain.append(("partner_id", "=", matched_partner.id))
                    open_inv = self.env["account.move"].search(inv_domain, limit=1)
                    if open_inv:
                        matched_partner = matched_partner or open_inv.partner_id
                        matched_invoice_note = f" [Matched {open_inv.name}]"

            full_label = f"{label} ({ref})" if ref else label
            line = self.env["account.bank.statement.line"].create({
                "journal_id": self.journal_id.id,
                "date": txn_date,
                "payment_ref": f"{full_label}{matched_invoice_note}",
                "amount": amount,
                "partner_id": matched_partner.id if matched_partner else False,
            })
            created_lines |= line

        self.result_summary = _(
            "Imported %s bank statement line(s) into %s. Matched %s line(s) via reconciliation rules."
        ) % (len(created_lines), self.journal_id.name, matched_rules)
        return {
            "type": "ir.actions.act_window",
            "name": _("Imported Bank Lines"),
            "res_model": "account.bank.statement.line",
            "view_mode": "list,form",
            "domain": [("id", "in", created_lines.ids)],
        }


class CustomFinancialStatementWizard(models.TransientModel):
    _name = "custom.financial.statement.wizard"
    _description = "Dynamic Financial Statements (P&L / Balance Sheet)"

    report_type = fields.Selection(
        [("pnl", "Profit & Loss Statement"), ("bs", "Balance Sheet")],
        default="pnl",
        required=True,
    )
    date_from = fields.Date(required=True, default=lambda self: fields.Date.today().replace(month=4, day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    line_ids = fields.One2many("custom.financial.statement.line", "wizard_id", string="Statement Lines")
    net_result = fields.Monetary(string="Net Profit / Net Balance", readonly=True)

    def action_compute_statement(self):
        self.ensure_one()
        self.line_ids.unlink()
        MoveLine = self.env["account.move.line"]
        if self.report_type == "pnl":
            account_types = ("income", "income_other", "expense", "expense_depreciation", "expense_direct_cost")
            domain = [
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("account_id.account_type", "in", account_types),
            ]
        else:
            account_types = (
                "asset_receivable", "asset_cash", "asset_current", "asset_non_current", "asset_prepayments", "asset_fixed",
                "liability_payable", "liability_credit_card", "liability_current", "liability_non_current", "equity", "equity_unaffected",
            )
            domain = [
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("date", "<=", self.date_to),
                ("account_id.account_type", "in", account_types),
            ]

        grouped = MoveLine._read_group(domain, ["account_id"], ["balance:sum"])
        lines = []
        total = 0.0
        for account, balance in grouped:
            if not account or round(balance, 2) == 0.0:
                continue
            display_amt = -balance if self.report_type == "pnl" else balance
            total += display_amt
            lines.append(Command.create({
                "account_id": account.id,
                "account_type": account.account_type,
                "balance": round(display_amt, 2),
            }))
        self.write({"line_ids": lines, "net_result": round(total, 2)})
        return {
            "type": "ir.actions.act_window",
            "name": _("Financial Statement"),
            "res_model": "custom.financial.statement.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class CustomFinancialStatementLine(models.TransientModel):
    _name = "custom.financial.statement.line"
    _description = "Dynamic Financial Statement Line"
    _order = "account_type, account_id"

    wizard_id = fields.Many2one("custom.financial.statement.wizard", required=True, ondelete="cascade")
    account_id = fields.Many2one("account.account", required=True, readonly=True)
    account_type = fields.Char(readonly=True)
    currency_id = fields.Many2one(related="wizard_id.currency_id", readonly=True)
    balance = fields.Monetary(readonly=True)
