import base64
import io
import re

from PyPDF2 import PdfReader

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


GSTIN_REGEX = re.compile(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b")
DATE_REGEX = re.compile(r"\b(20[0-9]{2}[-/][0-1]?[0-9][-/][0-3]?[0-9]|[0-3]?[0-9][-/][0-1]?[0-9][-/]20[0-9]{2})\b")
AMOUNT_REGEX = re.compile(r"(?:total|grand\s*total|net\s*amount|amount\s*payable|rs\.?|inr|₹)\s*[:\-]?\s*([0-9,]+\.?[0-9]{0,2})", re.IGNORECASE)
INV_NO_REGEX = re.compile(r"(?:inv(?:oice)?\s*(?:no\.?|#|number)?|bill\s*(?:no\.?|#))\s*[:\-]?\s*([A-Z0-9/\-]{3,25})", re.IGNORECASE)


class CustomBankReconcileWizard(models.TransientModel):
    _name = "custom.bank.reconcile.wizard"
    _description = "Interactive Bank Statement Reconciliation Console"

    journal_id = fields.Many2one(
        "account.journal",
        string="Bank / Cash Journal",
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    line_ids = fields.One2many("custom.bank.reconcile.line", "wizard_id", string="Unreconciled Transactions")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "line_ids" in fields_list:
            st_lines = self.env["account.bank.statement.line"].search(
                [("is_reconciled", "=", False)],
                order="date desc, id desc",
                limit=50,
            )
            Move = self.env["account.move"]
            lines = []
            for stl in st_lines:
                move_type = "out_invoice" if stl.amount > 0 else "in_invoice"
                domain = [
                    ("move_type", "=", move_type),
                    ("state", "=", "posted"),
                    ("payment_state", "in", ("not_paid", "partial")),
                    ("amount_residual", "=", abs(stl.amount)),
                ]
                if stl.partner_id:
                    domain.append(("partner_id", "=", stl.partner_id.id))
                matched = Move.search(domain, limit=1)
                lines.append(Command.create({
                    "statement_line_id": stl.id,
                    "suggested_move_id": matched.id if matched else False,
                }))
            res["line_ids"] = lines
        return res

    def action_reload_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        domain = [("is_reconciled", "=", False)]
        if self.journal_id:
            domain.append(("journal_id", "=", self.journal_id.id))
        st_lines = self.env["account.bank.statement.line"].search(domain, order="date desc, id desc", limit=50)
        Move = self.env["account.move"]
        vals = []
        for stl in st_lines:
            move_type = "out_invoice" if stl.amount > 0 else "in_invoice"
            inv_dom = [
                ("move_type", "=", move_type),
                ("state", "=", "posted"),
                ("payment_state", "in", ("not_paid", "partial")),
                ("amount_residual", "=", abs(stl.amount)),
            ]
            if stl.partner_id:
                inv_dom.append(("partner_id", "=", stl.partner_id.id))
            matched = Move.search(inv_dom, limit=1)
            vals.append(Command.create({
                "statement_line_id": stl.id,
                "suggested_move_id": matched.id if matched else False,
            }))
        self.line_ids = vals
        return {
            "type": "ir.actions.act_window",
            "name": _("Interactive Bank Reconciliation"),
            "res_model": "custom.bank.reconcile.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class CustomBankReconcileLine(models.TransientModel):
    _name = "custom.bank.reconcile.line"
    _description = "Interactive Bank Reconciliation Line"
    _order = "date desc, id desc"

    wizard_id = fields.Many2one("custom.bank.reconcile.wizard", required=True, ondelete="cascade")
    statement_line_id = fields.Many2one("account.bank.statement.line", required=True, readonly=True)
    date = fields.Date(related="statement_line_id.date", readonly=True)
    payment_ref = fields.Char(related="statement_line_id.payment_ref", readonly=True)
    partner_id = fields.Many2one(related="statement_line_id.partner_id", readonly=False)
    currency_id = fields.Many2one(related="statement_line_id.currency_id", readonly=True)
    amount = fields.Monetary(related="statement_line_id.amount", readonly=True)
    suggested_move_id = fields.Many2one(
        "account.move",
        string="Match Invoice / Vendor Bill",
        domain="[('move_type', 'in', ('out_invoice', 'in_invoice')), ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]",
    )
    counterpart_account_id = fields.Many2one(
        "account.account",
        string="Or Direct Expense / Income Account",
    )
    is_reconciled = fields.Boolean(related="statement_line_id.is_reconciled", readonly=True)

    def action_reconcile_line(self):
        for rec in self:
            stl = rec.statement_line_id
            if stl.is_reconciled:
                continue
            _liq, suspense_lines, _other = stl._seek_for_lines()
            if not suspense_lines:
                raise UserError(_("No open suspense line found on bank transaction %s.") % (stl.payment_ref or stl.id))
            suspense = suspense_lines[0]

            if rec.suggested_move_id:
                inv = rec.suggested_move_id
                target_lines = inv.line_ids.filtered(
                    lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable") and not l.reconciled
                )
                if not target_lines:
                    raise UserError(_("Selected invoice/bill %s has no open receivable/payable line.") % inv.name)
                target = target_lines[0]
                stl.move_id.button_draft()
                suspense.write({
                    "account_id": target.account_id.id,
                    "partner_id": inv.partner_id.id,
                })
                stl.move_id.action_post()
                (suspense + target).reconcile()
            elif rec.counterpart_account_id:
                stl.move_id.button_draft()
                suspense.write({
                    "account_id": rec.counterpart_account_id.id,
                    "partner_id": rec.partner_id.id if rec.partner_id else False,
                })
                stl.move_id.action_post()
            else:
                raise UserError(_("Select a matching Invoice/Bill or a Direct Counterpart Account first."))


class CustomBillOcrWizard(models.TransientModel):
    _name = "custom.bill.ocr.wizard"
    _description = "Vendor Bill PDF & Text OCR Extractor"

    pdf_file = fields.Binary(string="Vendor Bill PDF")
    pdf_filename = fields.Char()
    raw_text = fields.Text(string="Extracted / Pasted Bill Text")
    detected_gstin = fields.Char(string="Detected Vendor GSTIN")
    partner_id = fields.Many2one("res.partner", string="Matched Vendor")
    invoice_number = fields.Char(string="Detected Invoice #")
    invoice_date = fields.Date(string="Detected Date", default=fields.Date.context_today)
    detected_amount = fields.Float(string="Detected Total Amount")
    expense_account_id = fields.Many2one("account.account", string="Default Expense Account")

    def action_extract_fields(self):
        self.ensure_one()
        text = self.raw_text or ""
        if self.pdf_file:
            pdf_bytes = self.pdf_file.content if hasattr(self.pdf_file, "content") else base64.b64decode(self.pdf_file)
            reader = PdfReader(io.BytesIO(pdf_bytes))
            extracted_pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(extracted_pages).strip() or text

        if not text.strip():
            raise UserError(_("Upload a text-readable PDF or paste bill text before extracting."))

        gstin_match = GSTIN_REGEX.search(text.upper())
        inv_match = INV_NO_REGEX.search(text)
        amt_matches = AMOUNT_REGEX.findall(text)
        date_match = DATE_REGEX.search(text)

        gstin = gstin_match.group(1) if gstin_match else False
        vendor = self.env["res.partner"].search([("vat", "ilike", gstin)], limit=1) if gstin else False
        parsed_amount = 0.0
        if amt_matches:
            parsed_amount = float(amt_matches[-1].replace(",", ""))

        parsed_date = self.invoice_date
        if date_match:
            raw_d = date_match.group(1).replace("/", "-")
            parts = raw_d.split("-")
            if len(parts) == 3 and len(parts[2]) == 4:
                parsed_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            elif len(parts) == 3 and len(parts[0]) == 4:
                parsed_date = f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"

        self.write({
            "raw_text": text,
            "detected_gstin": gstin,
            "partner_id": vendor.id if vendor else self.partner_id.id,
            "invoice_number": inv_match.group(1) if inv_match else self.invoice_number,
            "invoice_date": parsed_date,
            "detected_amount": parsed_amount or self.detected_amount,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Bill OCR Extractor"),
            "res_model": "custom.bill.ocr.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_create_vendor_bill(self):
        self.ensure_one()
        if not self.raw_text and self.pdf_file:
            self.action_extract_fields()
        line_vals = {
            "name": f"OCR Extracted Bill ({self.invoice_number or 'Draft'})",
            "quantity": 1.0,
            "price_unit": self.detected_amount or 0.0,
        }
        if self.expense_account_id:
            line_vals["account_id"] = self.expense_account_id.id
        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.partner_id.id if self.partner_id else False,
            "ref": self.invoice_number or False,
            "invoice_date": self.invoice_date or fields.Date.today(),
            "invoice_line_ids": [Command.create(line_vals)],
        })
        if self.pdf_file:
            raw_bytes = self.pdf_file.content if hasattr(self.pdf_file, "content") else base64.b64decode(self.pdf_file)
            self.env["ir.attachment"].create({
                "name": self.pdf_filename or "vendor_bill.pdf",
                "raw": raw_bytes,
                "res_model": "account.move",
                "res_id": bill.id,
            })
        return {
            "type": "ir.actions.act_window",
            "name": _("Draft Vendor Bill"),
            "res_model": "account.move",
            "res_id": bill.id,
            "view_mode": "form",
        }


class AccountMoveLineAsset(models.Model):
    _inherit = "account.move.line"

    x_asset_category_id = fields.Many2one(
        "custom.asset.category",
        string="Auto-Create Asset Category",
        help="When this vendor bill is posted, an asset record is automatically generated in this category.",
    )
    x_generated_asset_id = fields.Many2one("custom.asset", string="Generated Asset", readonly=True, copy=False)


class AccountMoveAssetHook(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        res = super()._post(soft=soft)
        Asset = self.env["custom.asset"]
        for move in self.filtered(lambda m: m.move_type == "in_invoice"):
            for line in move.invoice_line_ids.filtered(lambda l: l.x_asset_category_id and not l.x_generated_asset_id and l.price_subtotal > 0):
                cat = line.x_asset_category_id
                asset = Asset.create({
                    "name": line.name or f"{move.name} Asset",
                    "category_id": cat.id,
                    "acquisition_date": move.invoice_date or move.date or fields.Date.today(),
                    "first_depreciation_date": move.invoice_date or move.date or fields.Date.today(),
                    "original_value": line.price_subtotal,
                    "method": cat.method,
                    "useful_life_months": cat.useful_life_months,
                    "degressive_rate": cat.degressive_rate,
                    "journal_id": cat.journal_id.id if cat.journal_id else False,
                    "depreciation_account_id": cat.depreciation_account_id.id if cat.depreciation_account_id else False,
                    "expense_account_id": cat.expense_account_id.id if cat.expense_account_id else False,
                    "company_id": move.company_id.id,
                })
                asset.action_compute_depreciation()
                line.x_generated_asset_id = asset.id
                move.message_post(body=_("Auto-created Fixed Asset %s (%s).") % (asset.name, asset.code))
        return res


class CustomConsolidationWizard(models.TransientModel):
    _name = "custom.consolidation.wizard"
    _description = "Multi-Company Consolidation & Cash Flow Statement"

    report_mode = fields.Selection(
        [("consolidation", "Multi-Company Consolidated P&L / Balance Sheet"), ("cashflow", "Cash Flow Summary (Operating / Investing / Financing)")],
        default="consolidation",
        required=True,
    )
    company_ids = fields.Many2many(
        "res.company",
        string="Companies to Consolidate",
        default=lambda self: self.env.companies,
        required=True,
    )
    date_from = fields.Date(required=True, default=lambda self: fields.Date.today().replace(month=4, day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    exclude_intercompany_partner_ids = fields.Many2many(
        "res.partner",
        string="Inter-Company Partners to Eliminate",
    )
    currency_id = fields.Many2one(related="company_ids.currency_id", readonly=True)
    line_ids = fields.One2many("custom.consolidation.line", "wizard_id", string="Consolidated Lines")
    total_amount = fields.Monetary(readonly=True)

    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        MoveLine = self.env["account.move.line"]
        domain = [
            ("company_id", "in", self.company_ids.ids),
            ("parent_state", "=", "posted"),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if self.exclude_intercompany_partner_ids:
            domain.append(("partner_id", "not in", self.exclude_intercompany_partner_ids.ids))

        if self.report_mode == "cashflow":
            domain.append(("journal_id.type", "in", ("bank", "cash")))

        grouped = MoveLine._read_group(domain, ["account_id"], ["balance:sum"])
        lines = []
        total = 0.0
        for account, balance in grouped:
            if not account or round(balance, 2) == 0.0:
                continue
            total += balance
            lines.append(Command.create({
                "account_code": account.code,
                "account_name": account.name,
                "account_type": account.account_type,
                "balance": round(balance, 2),
            }))
        self.write({"line_ids": lines, "total_amount": round(total, 2)})
        return {
            "type": "ir.actions.act_window",
            "name": _("Consolidation & Cash Flow"),
            "res_model": "custom.consolidation.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class CustomConsolidationLine(models.TransientModel):
    _name = "custom.consolidation.line"
    _description = "Consolidation / Cash Flow Line"
    _order = "account_code"

    wizard_id = fields.Many2one("custom.consolidation.wizard", required=True, ondelete="cascade")
    account_code = fields.Char(readonly=True)
    account_name = fields.Char(readonly=True)
    account_type = fields.Char(readonly=True)
    currency_id = fields.Many2one(related="wizard_id.currency_id", readonly=True)
    balance = fields.Monetary(readonly=True)


class CustomTaxLockWizard(models.TransientModel):
    _name = "custom.tax.lock.wizard"
    _description = "GST Tax & Accounting Period Lock Dates"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    tax_lock_date = fields.Date(string="Tax / GSTR Lock Date")
    fiscalyear_lock_date = fields.Date(string="All Users Period Lock Date")
    sale_lock_date = fields.Date(string="Sales Lock Date")
    purchase_lock_date = fields.Date(string="Purchase Lock Date")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        comp = self.env.company
        res.update({
            "company_id": comp.id,
            "tax_lock_date": comp.tax_lock_date,
            "fiscalyear_lock_date": comp.fiscalyear_lock_date,
            "sale_lock_date": comp.sale_lock_date,
            "purchase_lock_date": comp.purchase_lock_date,
        })
        return res

    def action_apply_locks(self):
        self.ensure_one()
        self.company_id.sudo().write({
            "tax_lock_date": self.tax_lock_date,
            "fiscalyear_lock_date": self.fiscalyear_lock_date,
            "sale_lock_date": self.sale_lock_date,
            "purchase_lock_date": self.purchase_lock_date,
        })


class CustomEquityHolder(models.Model):
    _name = "custom.equity.holder"
    _description = "Shareholder / Partner Equity Cap Table"
    _order = "total_shares desc, name"

    name = fields.Char(string="Shareholder / Partner", required=True)
    partner_id = fields.Many2one("res.partner", string="Linked Contact")
    share_class = fields.Selection(
        [("equity", "Common Equity Shares"), ("preference", "Preference Shares"), ("partner", "LLP / Partner Capital")],
        default="equity",
        required=True,
    )
    grant_ids = fields.One2many("custom.equity.grant", "holder_id", string="Allotments")
    total_shares = fields.Integer(compute="_compute_equity", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    total_capital = fields.Monetary(string="Paid-Up Capital", compute="_compute_equity", store=True)
    ownership_pct = fields.Float(string="Ownership %", compute="_compute_ownership_pct")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.depends("grant_ids.shares_count", "grant_ids.paid_amount")
    def _compute_equity(self):
        for holder in self:
            holder.total_shares = sum(holder.grant_ids.mapped("shares_count"))
            holder.total_capital = sum(holder.grant_ids.mapped("paid_amount"))

    @api.depends("total_shares")
    def _compute_ownership_pct(self):
        all_holders = self.search([])
        grand_shares = sum(all_holders.mapped("total_shares"))
        for holder in self:
            holder.ownership_pct = round((holder.total_shares / grand_shares * 100.0), 2) if grand_shares else 0.0


class CustomEquityGrant(models.Model):
    _name = "custom.equity.grant"
    _description = "Share Allotment / Capital Tranche"
    _order = "allotment_date desc"

    holder_id = fields.Many2one("custom.equity.holder", required=True, ondelete="cascade")
    certificate_no = fields.Char(string="Certificate / Folio #")
    allotment_date = fields.Date(required=True, default=fields.Date.context_today)
    shares_count = fields.Integer(string="Number of Shares", required=True, default=1000)
    face_value = fields.Float(string="Face Value / Share", default=10.0)
    currency_id = fields.Many2one(related="holder_id.currency_id", readonly=True)
    paid_amount = fields.Monetary(string="Total Paid Capital", required=True)
