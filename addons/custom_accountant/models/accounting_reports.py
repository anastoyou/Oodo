import base64
import csv
import io
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models


REPORT_TYPES = [
    ("pnl", "Profit and Loss"),
    ("balance_sheet", "Balance Sheet"),
    ("executive_summary", "Executive Summary"),
    ("cashflow", "Cash Flow Statement"),
    ("general_ledger", "General Ledger"),
    ("trial_balance", "Trial Balance"),
    ("partner_ledger", "Partner Ledger"),
    ("aged_receivable", "Aged Receivable"),
    ("aged_payable", "Aged Payable"),
    ("tax_report", "Tax Return / GST Summary"),
    ("journal_audit", "Journal Audit Report"),
]

INCOME_TYPES = ("income", "income_other")
COGS_TYPES = ("expense_direct_cost",)
OPEX_TYPES = ("expense", "expense_other")
DEPR_TYPES = ("expense_depreciation",)
PNL_TYPES = INCOME_TYPES + COGS_TYPES + OPEX_TYPES + DEPR_TYPES

ASSET_CASH_TYPES = ("asset_cash",)
ASSET_REC_TYPES = ("asset_receivable",)
ASSET_CUR_TYPES = ("asset_current", "asset_prepayments")
ASSET_NONCUR_TYPES = ("asset_non_current", "asset_fixed")
LIAB_PAY_TYPES = ("liability_payable",)
LIAB_CUR_TYPES = ("liability_credit_card", "liability_current")
LIAB_NONCUR_TYPES = ("liability_non_current",)
EQUITY_TYPES = ("equity", "equity_unaffected", "equity_retained")


def _default_fy_start(company):
    """Return the start date of the current fiscal year for company."""
    today = fields.Date.context_today(company)
    last_month = int(company.fiscalyear_last_month or 12)
    last_day = min(int(company.fiscalyear_last_day or 31), 28 if last_month == 2 else 31)
    try:
        fy_end = today.replace(month=last_month, day=last_day)
    except ValueError:
        fy_end = today.replace(month=last_month, day=28)
    if today > fy_end:
        fy_end = fy_end + relativedelta(years=1)
    return fy_end - relativedelta(years=1) + timedelta(days=1)


class CustomAccountingReport(models.TransientModel):
    _name = "custom.accounting.report"
    _description = "Enterprise Dynamic Financial & Audit Report"

    name = fields.Char(compute="_compute_name")
    report_type = fields.Selection(REPORT_TYPES, required=True, default="pnl")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    date_from = fields.Date(
        string="From Date",
        required=True,
        default=lambda self: _default_fy_start(self.env.company),
    )
    date_to = fields.Date(string="As Of / To Date", required=True, default=fields.Date.context_today)
    compare_previous = fields.Boolean(string="Compare Previous Period", default=False)
    include_unposted = fields.Boolean(string="Include Draft Entries", default=False)
    hide_zero = fields.Boolean(string="Hide Zero Rows", default=True)
    partner_ids = fields.Many2many("res.partner", string="Filter Partners")
    journal_ids = fields.Many2many("account.journal", string="Filter Journals")
    analytic_account_ids = fields.Many2many("account.analytic.account", string="Analytic Accounts")
    line_ids = fields.One2many("custom.accounting.report.line", "report_id", string="Report Lines")
    summary_headline = fields.Char(readonly=True)
    primary_total = fields.Monetary(string="Headline Total", readonly=True)
    secondary_total = fields.Monetary(string="Comparison / Secondary Total", readonly=True)

    @api.depends("report_type", "date_from", "date_to")
    def _compute_name(self):
        label_map = dict(REPORT_TYPES)
        for rec in self:
            rec.name = f"{label_map.get(rec.report_type, 'Report')} ({rec.date_from} → {rec.date_to})"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        rtype = self.env.context.get("default_report_type") or res.get("report_type") or "pnl"
        res["report_type"] = rtype
        return res

    @api.model
    def action_open_report(self, report_type="pnl"):
        """Create and immediately compute an interactive Enterprise report."""
        company = self.env.company
        wizard = self.create({
            "report_type": report_type,
            "company_id": company.id,
            "date_from": _default_fy_start(company),
            "date_to": fields.Date.context_today(self),
        })
        wizard._compute_report_lines()
        label = dict(REPORT_TYPES).get(report_type, _("Financial Report"))
        return {
            "type": "ir.actions.act_window",
            "name": label,
            "res_model": "custom.accounting.report",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_recompute(self):
        self.ensure_one()
        self._compute_report_lines()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "custom.accounting.report",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def _base_domain(self, date_from=None, date_to=None):
        self.ensure_one()
        domain = [("company_id", "=", self.company_id.id)]
        if not self.include_unposted:
            domain.append(("parent_state", "=", "posted"))
        else:
            domain.append(("parent_state", "!=", "cancel"))
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        return domain

    def _filter_analytic(self, aml_rows):
        if not self.analytic_account_ids:
            return aml_rows
        keys = {str(aid) for aid in self.analytic_account_ids.ids}
        return aml_rows.filtered(
            lambda l: l.analytic_distribution and any(k in l.analytic_distribution for k in keys)
        )

    def _previous_period_dates(self):
        self.ensure_one()
        delta_days = (self.date_to - self.date_from).days + 1
        prev_to = self.date_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=max(delta_days - 1, 0))
        return prev_from, prev_to

    def _sum_by_account(self, date_from, date_to, account_types=None):
        domain = self._base_domain(date_from=date_from, date_to=date_to)
        if account_types:
            domain.append(("account_id.account_type", "in", account_types))
        MoveLine = self.env["account.move.line"]
        if self.analytic_account_ids:
            rows = self._filter_analytic(MoveLine.search(domain))
            totals = {}
            for r in rows:
                acc = r.account_id
                d = totals.setdefault(acc, {"debit": 0.0, "credit": 0.0, "balance": 0.0})
                d["debit"] += r.debit
                d["credit"] += r.credit
                d["balance"] += r.balance
            return totals
        grouped = MoveLine._read_group(domain, ["account_id"], ["debit:sum", "credit:sum", "balance:sum"])
        return {
            acc: {"debit": debit, "credit": credit, "balance": balance}
            for acc, debit, credit, balance in grouped
            if acc
        }

    def _line_dict(self, seq, name, line_type="detail", level=1, code="", account_id=False,
                   partner_id=False, journal_id=False, tax_id=False,
                   amount=0.0, compare_amount=0.0, debit=0.0, credit=0.0,
                   initial_balance=0.0, bucket_0=0.0, bucket_30=0.0, bucket_60=0.0,
                   bucket_90=0.0, bucket_120=0.0, bucket_older=0.0, is_ratio=False,
                   extra_domain=""):
        variance = amount - compare_amount if self.compare_previous else 0.0
        variance_pct = (variance / abs(compare_amount) * 100.0) if (self.compare_previous and compare_amount) else 0.0
        return Command.create({
            "sequence": seq,
            "name": name,
            "line_type": line_type,
            "level": level,
            "code": code,
            "account_id": account_id,
            "partner_id": partner_id,
            "journal_id": journal_id,
            "tax_id": tax_id,
            "amount": round(amount, 2),
            "compare_amount": round(compare_amount, 2),
            "variance": round(variance, 2),
            "variance_pct": round(variance_pct, 2),
            "debit": round(debit, 2),
            "credit": round(credit, 2),
            "initial_balance": round(initial_balance, 2),
            "bucket_0": round(bucket_0, 2),
            "bucket_30": round(bucket_30, 2),
            "bucket_60": round(bucket_60, 2),
            "bucket_90": round(bucket_90, 2),
            "bucket_120": round(bucket_120, 2),
            "bucket_older": round(bucket_older, 2),
            "is_ratio": is_ratio,
            "extra_domain": extra_domain,
        })

    def _compute_report_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        handler = {
            "pnl": self._build_pnl,
            "balance_sheet": self._build_balance_sheet,
            "executive_summary": self._build_executive_summary,
            "cashflow": self._build_cashflow,
            "general_ledger": self._build_general_ledger,
            "trial_balance": self._build_trial_balance,
            "partner_ledger": self._build_partner_ledger,
            "aged_receivable": lambda: self._build_aged_partner("asset_receivable"),
            "aged_payable": lambda: self._build_aged_partner("liability_payable"),
            "tax_report": self._build_tax_report,
            "journal_audit": self._build_journal_audit,
        }.get(self.report_type, self._build_pnl)
        lines, headline, primary, secondary = handler()
        self.write({
            "line_ids": lines,
            "summary_headline": headline,
            "primary_total": round(primary, 2),
            "secondary_total": round(secondary, 2),
        })

    def _build_pnl(self):
        cur_data = self._sum_by_account(self.date_from, self.date_to, PNL_TYPES)
        prev_from, prev_to = self._previous_period_dates()
        prev_data = self._sum_by_account(prev_from, prev_to, PNL_TYPES) if self.compare_previous else {}

        all_accs = sorted(set(cur_data.keys()) | set(prev_data.keys()), key=lambda a: (a.code or "", a.name or ""))
        lines = []
        seq = 10

        def add_section(title, types, negate=True):
            nonlocal seq
            lines.append(self._line_dict(seq, title, line_type="section", level=0))
            seq += 10
            sec_cur = 0.0
            sec_prev = 0.0
            for acc in all_accs:
                if acc.account_type not in types:
                    continue
                val = cur_data.get(acc, {}).get("balance", 0.0)
                pval = prev_data.get(acc, {}).get("balance", 0.0)
                disp = -val if negate else val
                pdisp = -pval if negate else pval
                if self.hide_zero and round(disp, 2) == 0.0 and round(pdisp, 2) == 0.0:
                    continue
                sec_cur += disp
                sec_prev += pdisp
                lines.append(self._line_dict(
                    seq, f"{acc.code} {acc.name}", line_type="detail", level=1,
                    code=acc.code, account_id=acc.id, amount=disp, compare_amount=pdisp,
                ))
                seq += 10
            lines.append(self._line_dict(seq, f"Total {title}", line_type="subtotal", level=0, amount=sec_cur, compare_amount=sec_prev))
            seq += 10
            return sec_cur, sec_prev

        inc_c, inc_p = add_section(_("Operating Income"), ("income",), negate=True)
        other_inc_c, other_inc_p = add_section(_("Other Income"), ("income_other",), negate=True)
        cogs_c, cogs_p = add_section(_("Cost of Revenue"), COGS_TYPES, negate=False)

        gross_c = (inc_c + other_inc_c) - cogs_c
        gross_p = (inc_p + other_inc_p) - cogs_p
        lines.append(self._line_dict(seq, _("Gross Profit"), line_type="total", level=0, amount=gross_c, compare_amount=gross_p))
        seq += 10

        opex_c, opex_p = add_section(_("Operating Expenses"), OPEX_TYPES, negate=False)
        depr_c, depr_p = add_section(_("Depreciation & Amortization"), DEPR_TYPES, negate=False)

        net_c = gross_c - opex_c - depr_c
        net_p = gross_p - opex_p - depr_p
        lines.append(self._line_dict(seq, _("Net Profit / (Loss)"), line_type="total", level=0, amount=net_c, compare_amount=net_p))
        return lines, _("Net Profit"), net_c, net_p

    def _build_balance_sheet(self):
        cur_data = self._sum_by_account(None, self.date_to)
        prev_from, prev_to = self._previous_period_dates()
        prev_data = self._sum_by_account(None, prev_to) if self.compare_previous else {}
        all_accs = sorted(set(cur_data.keys()) | set(prev_data.keys()), key=lambda a: (a.code or "", a.name or ""))
        lines = []
        seq = 10

        def add_section(title, types, sign=1.0):
            nonlocal seq
            lines.append(self._line_dict(seq, title, line_type="section", level=0))
            seq += 10
            sec_c = 0.0
            sec_p = 0.0
            for acc in all_accs:
                if acc.account_type not in types:
                    continue
                disp = cur_data.get(acc, {}).get("balance", 0.0) * sign
                pdisp = prev_data.get(acc, {}).get("balance", 0.0) * sign
                if self.hide_zero and round(disp, 2) == 0.0 and round(pdisp, 2) == 0.0:
                    continue
                sec_c += disp
                sec_p += pdisp
                lines.append(self._line_dict(
                    seq, f"{acc.code} {acc.name}", line_type="detail", level=1,
                    code=acc.code, account_id=acc.id, amount=disp, compare_amount=pdisp,
                ))
                seq += 10
            lines.append(self._line_dict(seq, f"Total {title}", line_type="subtotal", level=0, amount=sec_c, compare_amount=sec_p))
            seq += 10
            return sec_c, sec_p

        lines.append(self._line_dict(seq, _("ASSETS"), line_type="section", level=0))
        seq += 10
        cash_c, cash_p = add_section(_("Bank and Cash Accounts"), ASSET_CASH_TYPES, 1.0)
        rec_c, rec_p = add_section(_("Receivables"), ASSET_REC_TYPES, 1.0)
        cur_a_c, cur_a_p = add_section(_("Current Assets & Prepayments"), ASSET_CUR_TYPES, 1.0)
        noncur_a_c, noncur_a_p = add_section(_("Fixed & Non-Current Assets"), ASSET_NONCUR_TYPES, 1.0)
        total_assets_c = cash_c + rec_c + cur_a_c + noncur_a_c
        total_assets_p = cash_p + rec_p + cur_a_p + noncur_a_p
        lines.append(self._line_dict(seq, _("TOTAL ASSETS"), line_type="total", level=0, amount=total_assets_c, compare_amount=total_assets_p))
        seq += 10

        lines.append(self._line_dict(seq, _("LIABILITIES & EQUITY"), line_type="section", level=0))
        seq += 10
        pay_c, pay_p = add_section(_("Payables"), LIAB_PAY_TYPES, -1.0)
        cur_l_c, cur_l_p = add_section(_("Current Liabilities & Credit Cards"), LIAB_CUR_TYPES, -1.0)
        noncur_l_c, noncur_l_p = add_section(_("Non-Current Liabilities"), LIAB_NONCUR_TYPES, -1.0)
        total_liab_c = pay_c + cur_l_c + noncur_l_c
        total_liab_p = pay_p + cur_l_p + noncur_l_p
        lines.append(self._line_dict(seq, _("Total Liabilities"), line_type="subtotal", level=0, amount=total_liab_c, compare_amount=total_liab_p))
        seq += 10

        eq_c, eq_p = add_section(_("Equity"), EQUITY_TYPES, -1.0)
        # Unallocated Earnings from P&L accounts up to date_to
        unalloc_c = -sum(v["balance"] for a, v in cur_data.items() if a.account_type in PNL_TYPES)
        unalloc_p = -sum(v["balance"] for a, v in prev_data.items() if a.account_type in PNL_TYPES) if prev_data else 0.0
        lines.append(self._line_dict(
            seq, _("Current / Unallocated Earnings"), line_type="detail", level=1,
            amount=unalloc_c, compare_amount=unalloc_p,
        ))
        seq += 10
        total_eq_c = eq_c + unalloc_c
        total_eq_p = eq_p + unalloc_p
        lines.append(self._line_dict(seq, _("Total Equity"), line_type="subtotal", level=0, amount=total_eq_c, compare_amount=total_eq_p))
        seq += 10

        total_le_c = total_liab_c + total_eq_c
        total_le_p = total_liab_p + total_eq_p
        lines.append(self._line_dict(seq, _("TOTAL LIABILITIES & EQUITY"), line_type="total", level=0, amount=total_le_c, compare_amount=total_le_p))
        return lines, _("Total Assets"), total_assets_c, total_le_c

    def _build_executive_summary(self):
        pnl_data = self._sum_by_account(self.date_from, self.date_to, PNL_TYPES)
        bs_data = self._sum_by_account(None, self.date_to)

        rev = -sum(v["balance"] for a, v in pnl_data.items() if a.account_type in INCOME_TYPES)
        cogs = sum(v["balance"] for a, v in pnl_data.items() if a.account_type in COGS_TYPES)
        opex = sum(v["balance"] for a, v in pnl_data.items() if a.account_type in (OPEX_TYPES + DEPR_TYPES))
        gross = rev - cogs
        net = gross - opex

        cash = sum(v["balance"] for a, v in bs_data.items() if a.account_type in ASSET_CASH_TYPES)
        ar = sum(v["balance"] for a, v in bs_data.items() if a.account_type in ASSET_REC_TYPES)
        other_ca = sum(v["balance"] for a, v in bs_data.items() if a.account_type in ASSET_CUR_TYPES)
        ap = -sum(v["balance"] for a, v in bs_data.items() if a.account_type in LIAB_PAY_TYPES)
        other_cl = -sum(v["balance"] for a, v in bs_data.items() if a.account_type in LIAB_CUR_TYPES)

        cur_assets = cash + ar + other_ca
        cur_liab = ap + other_cl
        gross_margin = (gross / rev * 100.0) if rev else 0.0
        net_margin = (net / rev * 100.0) if rev else 0.0
        cur_ratio = (cur_assets / cur_liab) if cur_liab else 0.0
        quick_ratio = ((cash + ar) / cur_liab) if cur_liab else 0.0

        days = max((self.date_to - self.date_from).days + 1, 1)
        dso = (ar / rev * days) if rev else 0.0
        dpo = (ap / cogs * days) if cogs else 0.0

        lines = [
            self._line_dict(10, _("Profitability"), line_type="section", level=0),
            self._line_dict(20, _("Revenue"), amount=rev),
            self._line_dict(30, _("Cost of Revenue"), amount=cogs),
            self._line_dict(40, _("Gross Profit"), line_type="subtotal", level=0, amount=gross),
            self._line_dict(50, _("Operating Expenses & Depreciation"), amount=opex),
            self._line_dict(60, _("Net Profit"), line_type="total", level=0, amount=net),
            self._line_dict(70, _("Gross Margin (%)"), amount=gross_margin, is_ratio=True),
            self._line_dict(80, _("Net Profit Margin (%)"), amount=net_margin, is_ratio=True),
            self._line_dict(90, _("Liquidity & Working Capital"), line_type="section", level=0),
            self._line_dict(100, _("Cash & Bank Balance"), amount=cash),
            self._line_dict(110, _("Accounts Receivable"), amount=ar),
            self._line_dict(120, _("Accounts Payable"), amount=ap),
            self._line_dict(130, _("Current Ratio"), amount=cur_ratio, is_ratio=True),
            self._line_dict(140, _("Quick Ratio"), amount=quick_ratio, is_ratio=True),
            self._line_dict(150, _("Days Sales Outstanding (DSO - Days)"), amount=dso, is_ratio=True),
            self._line_dict(160, _("Days Payable Outstanding (DPO - Days)"), amount=dpo, is_ratio=True),
        ]
        return lines, _("Net Profit"), net, cash

    def _build_cashflow(self):
        # Compute opening cash (prior to date_from) and period cash movements categorized by counterparty account types
        opening_data = self._sum_by_account(None, self.date_from - timedelta(days=1), ASSET_CASH_TYPES)
        opening_cash = sum(v["balance"] for v in opening_data.values())

        MoveLine = self.env["account.move.line"]
        domain = self._base_domain(self.date_from, self.date_to) + [("account_id.account_type", "in", ASSET_CASH_TYPES)]
        cash_lines = self._filter_analytic(MoveLine.search(domain))

        operating = 0.0
        investing = 0.0
        financing = 0.0
        move_ids = cash_lines.mapped("move_id")
        # Classify each cash move based on non-cash counterpart line account types
        for move in move_ids:
            cash_amt = sum(move.line_ids.filtered(lambda l: l.account_id.account_type in ASSET_CASH_TYPES).mapped("balance"))
            other_types = set(move.line_ids.filtered(lambda l: l.account_id.account_type not in ASSET_CASH_TYPES).mapped("account_id.account_type"))
            if other_types & set(ASSET_NONCUR_TYPES):
                investing += cash_amt
            elif other_types & (set(LIAB_NONCUR_TYPES) | set(EQUITY_TYPES)):
                financing += cash_amt
            else:
                operating += cash_amt

        net_change = operating + investing + financing
        closing_cash = opening_cash + net_change

        lines = [
            self._line_dict(10, _("Opening Cash & Bank Balance"), line_type="subtotal", level=0, amount=opening_cash),
            self._line_dict(20, _("Cash Flows from Operating Activities"), line_type="section", level=0),
            self._line_dict(30, _("Net Cash from Operations (Customers, Suppliers, Taxes, Payroll)"), amount=operating),
            self._line_dict(40, _("Cash Flows from Investing Activities"), line_type="section", level=0),
            self._line_dict(50, _("Fixed Assets & Long-Term Investments"), amount=investing),
            self._line_dict(60, _("Cash Flows from Financing Activities"), line_type="section", level=0),
            self._line_dict(70, _("Equity Capital & Long-Term Borrowings"), amount=financing),
            self._line_dict(80, _("Net Increase / (Decrease) in Cash"), line_type="subtotal", level=0, amount=net_change),
            self._line_dict(90, _("Closing Cash & Bank Balance"), line_type="total", level=0, amount=closing_cash),
        ]
        return lines, _("Closing Cash"), closing_cash, net_change

    def _build_general_ledger(self):
        init_data = self._sum_by_account(None, self.date_from - timedelta(days=1))
        period_data = self._sum_by_account(self.date_from, self.date_to)
        all_accs = sorted(set(init_data.keys()) | set(period_data.keys()), key=lambda a: (a.code or "", a.name or ""))
        lines = []
        seq = 10
        tot_init = tot_deb = tot_cred = tot_end = 0.0
        for acc in all_accs:
            init_b = init_data.get(acc, {}).get("balance", 0.0)
            p_deb = period_data.get(acc, {}).get("debit", 0.0)
            p_cred = period_data.get(acc, {}).get("credit", 0.0)
            end_b = init_b + p_deb - p_cred
            if self.hide_zero and round(init_b, 2) == 0.0 and round(p_deb, 2) == 0.0 and round(p_cred, 2) == 0.0:
                continue
            tot_init += init_b
            tot_deb += p_deb
            tot_cred += p_cred
            tot_end += end_b
            lines.append(self._line_dict(
                seq, f"{acc.code} {acc.name}", line_type="detail", level=1,
                code=acc.code, account_id=acc.id,
                initial_balance=init_b, debit=p_deb, credit=p_cred, amount=end_b,
            ))
            seq += 10
        lines.append(self._line_dict(
            seq, _("Grand Total"), line_type="total", level=0,
            initial_balance=tot_init, debit=tot_deb, credit=tot_cred, amount=tot_end,
        ))
        return lines, _("Period Debit / Credit"), tot_deb, tot_cred

    def _build_trial_balance(self):
        return self._build_general_ledger()

    def _build_partner_ledger(self):
        MoveLine = self.env["account.move.line"]
        base = [("account_id.account_type", "in", ("asset_receivable", "liability_payable")), ("partner_id", "!=", False)]
        init_domain = self._base_domain(None, self.date_from - timedelta(days=1)) + base
        period_domain = self._base_domain(self.date_from, self.date_to) + base

        init_grp = MoveLine._read_group(init_domain, ["partner_id"], ["balance:sum"])
        period_grp = MoveLine._read_group(period_domain, ["partner_id"], ["debit:sum", "credit:sum", "balance:sum"])

        init_map = {p: bal for p, bal in init_grp if p}
        per_map = {p: (d, c, b) for p, d, c, b in period_grp if p}
        all_partners = sorted(set(init_map.keys()) | set(per_map.keys()), key=lambda p: (p.name or "").lower())

        lines = []
        seq = 10
        tot_init = tot_deb = tot_cred = tot_end = 0.0
        for p in all_partners:
            init_b = init_map.get(p, 0.0)
            p_deb, p_cred, p_bal = per_map.get(p, (0.0, 0.0, 0.0))
            end_b = init_b + p_bal
            if self.hide_zero and round(init_b, 2) == 0.0 and round(p_deb, 2) == 0.0 and round(p_cred, 2) == 0.0 and round(end_b, 2) == 0.0:
                continue
            tot_init += init_b
            tot_deb += p_deb
            tot_cred += p_cred
            tot_end += end_b
            lines.append(self._line_dict(
                seq, p.display_name, line_type="detail", level=1,
                partner_id=p.id, initial_balance=init_b, debit=p_deb, credit=p_cred, amount=end_b,
            ))
            seq += 10
        lines.append(self._line_dict(
            seq, _("Total Partners"), line_type="total", level=0,
            initial_balance=tot_init, debit=tot_deb, credit=tot_cred, amount=tot_end,
        ))
        return lines, _("Net Partner Balance"), tot_end, tot_deb

    def _build_aged_partner(self, account_type):
        MoveLine = self.env["account.move.line"]
        as_of = self.date_to
        sign = 1.0 if account_type == "asset_receivable" else -1.0
        domain = self._base_domain(None, as_of) + [
            ("account_id.account_type", "=", account_type),
            ("reconciled", "=", False),
            ("amount_residual", "!=", 0.0),
        ]
        open_lines = self._filter_analytic(MoveLine.search(domain))
        by_partner = {}
        for l in open_lines:
            partner = l.partner_id
            key = partner.id if partner else 0
            entry = by_partner.setdefault(key, {
                "partner": partner, "b0": 0.0, "b30": 0.0, "b60": 0.0, "b90": 0.0, "b120": 0.0, "older": 0.0,
            })
            due_date = l.date_maturity or l.date
            days_over = (as_of - due_date).days
            amt = l.amount_residual * sign
            if days_over <= 0:
                entry["b0"] += amt
            elif days_over <= 30:
                entry["b30"] += amt
            elif days_over <= 60:
                entry["b60"] += amt
            elif days_over <= 90:
                entry["b90"] += amt
            elif days_over <= 120:
                entry["b120"] += amt
            else:
                entry["older"] += amt

        lines = []
        seq = 10
        tb0 = tb30 = tb60 = tb90 = tb120 = tolder = 0.0
        for row in sorted(by_partner.values(), key=lambda r: (r["partner"].name if r["partner"] else "Unknown").lower()):
            total = row["b0"] + row["b30"] + row["b60"] + row["b90"] + row["b120"] + row["older"]
            if self.hide_zero and round(total, 2) == 0.0:
                continue
            tb0 += row["b0"]
            tb30 += row["b30"]
            tb60 += row["b60"]
            tb90 += row["b90"]
            tb120 += row["b120"]
            tolder += row["older"]
            p = row["partner"]
            lines.append(self._line_dict(
                seq, p.display_name if p else _("Unassigned Partner"),
                line_type="detail", level=1, partner_id=p.id if p else False,
                bucket_0=row["b0"], bucket_30=row["b30"], bucket_60=row["b60"],
                bucket_90=row["b90"], bucket_120=row["b120"], bucket_older=row["older"],
                amount=total,
            ))
            seq += 10
        grand = tb0 + tb30 + tb60 + tb90 + tb120 + tolder
        lines.append(self._line_dict(
            seq, _("Total"), line_type="total", level=0,
            bucket_0=tb0, bucket_30=tb30, bucket_60=tb60,
            bucket_90=tb90, bucket_120=tb120, bucket_older=tolder,
            amount=grand,
        ))
        title = _("Total Receivable") if account_type == "asset_receivable" else _("Total Payable")
        return lines, title, grand, grand - tb0

    def _build_tax_report(self):
        MoveLine = self.env["account.move.line"]
        domain = self._base_domain(self.date_from, self.date_to) + [("tax_line_id", "!=", False)]
        grouped = MoveLine._read_group(domain, ["tax_line_id"], ["tax_base_amount:sum", "balance:sum"])

        sales_rows = []
        purchase_rows = []
        other_rows = []
        for tax, base_amt, tax_bal in grouped:
            if not tax:
                continue
            if tax.type_tax_use == "sale":
                sales_rows.append((tax, base_amt, -tax_bal))
            elif tax.type_tax_use == "purchase":
                purchase_rows.append((tax, base_amt, tax_bal))
            else:
                other_rows.append((tax, base_amt, -tax_bal))

        lines = []
        seq = 10
        lines.append(self._line_dict(seq, _("Output Taxes (Sales / GSTR-1)"), line_type="section", level=0))
        seq += 10
        out_tax_tot = 0.0
        for tax, base_amt, tax_amt in sorted(sales_rows, key=lambda r: r[0].name):
            out_tax_tot += tax_amt
            lines.append(self._line_dict(
                seq, tax.name, line_type="detail", level=1, tax_id=tax.id,
                initial_balance=base_amt, amount=tax_amt,
            ))
            seq += 10
        lines.append(self._line_dict(seq, _("Total Output Tax"), line_type="subtotal", level=0, amount=out_tax_tot))
        seq += 10

        lines.append(self._line_dict(seq, _("Input Taxes / ITC (Purchases / GSTR-2B)"), line_type="section", level=0))
        seq += 10
        in_tax_tot = 0.0
        for tax, base_amt, tax_amt in sorted(purchase_rows, key=lambda r: r[0].name):
            in_tax_tot += tax_amt
            lines.append(self._line_dict(
                seq, tax.name, line_type="detail", level=1, tax_id=tax.id,
                initial_balance=base_amt, amount=tax_amt,
            ))
            seq += 10
        lines.append(self._line_dict(seq, _("Total Input Tax Credit"), line_type="subtotal", level=0, amount=in_tax_tot))
        seq += 10

        if other_rows:
            lines.append(self._line_dict(seq, _("Other Taxes"), line_type="section", level=0))
            seq += 10
            for tax, base_amt, tax_amt in other_rows:
                out_tax_tot += tax_amt
                lines.append(self._line_dict(
                    seq, tax.name, line_type="detail", level=1, tax_id=tax.id,
                    initial_balance=base_amt, amount=tax_amt,
                ))
                seq += 10

        net_tax = out_tax_tot - in_tax_tot
        lines.append(self._line_dict(seq, _("Net Tax Payable / (Refundable)"), line_type="total", level=0, amount=net_tax))
        return lines, _("Net Tax Payable"), net_tax, out_tax_tot

    def _build_journal_audit(self):
        MoveLine = self.env["account.move.line"]
        domain = self._base_domain(self.date_from, self.date_to)
        grouped = MoveLine._read_group(domain, ["journal_id"], ["debit:sum", "credit:sum", "balance:sum"])
        lines = []
        seq = 10
        tot_deb = tot_cred = 0.0
        for journal, deb, cred, bal in sorted(grouped, key=lambda r: (r[0].code if r[0] else "")):
            if not journal:
                continue
            if self.hide_zero and round(deb, 2) == 0.0 and round(cred, 2) == 0.0:
                continue
            tot_deb += deb
            tot_cred += cred
            lines.append(self._line_dict(
                seq, f"[{journal.code}] {journal.name} ({journal.type.title()})",
                line_type="detail", level=1, code=journal.code, journal_id=journal.id,
                debit=deb, credit=cred, amount=bal,
            ))
            seq += 10
        lines.append(self._line_dict(seq, _("Total Audited"), line_type="total", level=0, debit=tot_deb, credit=tot_cred, amount=tot_deb - tot_cred))
        return lines, _("Total Journal Volume"), tot_deb, tot_cred

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("custom_accountant.action_report_custom_accounting_pdf").report_action(self)

    def action_export_csv(self):
        self.ensure_one()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Section / Name", "Code", "Initial / Tax Base", "Debit", "Credit",
            "Amount / Ending", "Compare", "Variance",
            "Not Due", "1-30", "31-60", "61-90", "91-120", "Older",
        ])
        for line in self.line_ids:
            writer.writerow([
                line.name or "",
                line.code or "",
                line.initial_balance,
                line.debit,
                line.credit,
                line.amount,
                line.compare_amount,
                line.variance,
                line.bucket_0,
                line.bucket_30,
                line.bucket_60,
                line.bucket_90,
                line.bucket_120,
                line.bucket_older,
            ])
        raw_bytes = buf.getvalue().encode("utf-8")
        fname = f"{self.report_type}_{self.date_from}_{self.date_to}.csv"
        att = self.env["ir.attachment"].create({
            "name": fname,
            "type": "binary",
            "raw": raw_bytes,
            "mimetype": "text/csv",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{att.id}?download=true",
            "target": "self",
        }


class CustomAccountingReportLine(models.TransientModel):
    _name = "custom.accounting.report.line"
    _description = "Enterprise Financial Report Line"
    _order = "sequence, id"

    report_id = fields.Many2one("custom.accounting.report", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="report_id.currency_id", readonly=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(readonly=True)
    name = fields.Char(readonly=True)
    line_type = fields.Selection(
        [("section", "Section"), ("detail", "Account / Item"), ("subtotal", "Subtotal"), ("total", "Total")],
        default="detail",
        readonly=True,
    )
    level = fields.Integer(default=1)
    account_id = fields.Many2one("account.account", readonly=True)
    partner_id = fields.Many2one("res.partner", readonly=True)
    journal_id = fields.Many2one("account.journal", readonly=True)
    tax_id = fields.Many2one("account.tax", readonly=True)
    initial_balance = fields.Monetary(string="Opening / Base", readonly=True)
    debit = fields.Monetary(readonly=True)
    credit = fields.Monetary(readonly=True)
    amount = fields.Monetary(string="Balance / Amount", readonly=True)
    compare_amount = fields.Monetary(string="Previous Period", readonly=True)
    variance = fields.Monetary(readonly=True)
    variance_pct = fields.Float(string="Var %", readonly=True)
    bucket_0 = fields.Monetary(string="Not Due", readonly=True)
    bucket_30 = fields.Monetary(string="1-30", readonly=True)
    bucket_60 = fields.Monetary(string="31-60", readonly=True)
    bucket_90 = fields.Monetary(string="61-90", readonly=True)
    bucket_120 = fields.Monetary(string="91-120", readonly=True)
    bucket_older = fields.Monetary(string="Older", readonly=True)
    is_ratio = fields.Boolean(default=False)
    extra_domain = fields.Char()

    def action_open_journal_items(self):
        """Drill down from any report line to the underlying account.move.line records."""
        self.ensure_one()
        rep = self.report_id
        if rep.report_type in ("balance_sheet", "aged_receivable", "aged_payable"):
            domain = rep._base_domain(None, rep.date_to)
        else:
            domain = rep._base_domain(rep.date_from, rep.date_to)
        if self.account_id:
            domain.append(("account_id", "=", self.account_id.id))
        if self.partner_id:
            domain.append(("partner_id", "=", self.partner_id.id))
        if self.journal_id:
            domain.append(("journal_id", "=", self.journal_id.id))
        if self.tax_id:
            domain.append(("tax_line_id", "=", self.tax_id.id))
        if rep.report_type == "aged_receivable":
            domain.extend([("account_id.account_type", "=", "asset_receivable"), ("reconciled", "=", False)])
        elif rep.report_type == "aged_payable":
            domain.extend([("account_id.account_type", "=", "liability_payable"), ("reconciled", "=", False)])
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Items: %s") % (self.name or ""),
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "domain": domain,
            "context": {"create": False},
        }
