from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class CustomAssetEnterpriseExt(models.Model):
    _inherit = "custom.asset"

    disposal_move_id = fields.Many2one("account.move", string="Disposal Journal Entry", readonly=True, copy=False)
    disposal_date = fields.Date(string="Disposal Date", readonly=True, copy=False)
    disposal_proceeds = fields.Monetary(string="Sale Proceeds", readonly=True, copy=False)

    def action_open_disposal_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Sell or Dispose Asset"),
            "res_model": "custom.asset.disposal.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_asset_id": self.id},
        }

    def action_open_modify_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Modify / Revalue Asset"),
            "res_model": "custom.asset.modify.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_asset_id": self.id,
                "default_useful_life_months": self.useful_life_months,
                "default_salvage_value": self.salvage_value,
            },
        }


class CustomAssetDisposalWizard(models.TransientModel):
    _name = "custom.asset.disposal.wizard"
    _description = "Fixed Asset Sell / Scrap / Disposal Wizard"

    asset_id = fields.Many2one("custom.asset", required=True, readonly=True)
    currency_id = fields.Many2one(related="asset_id.currency_id", readonly=True)
    disposal_type = fields.Selection(
        [("dispose", "Write-Off / Scrap"), ("sell", "Sell Asset")],
        default="dispose",
        required=True,
    )
    disposal_date = fields.Date(required=True, default=fields.Date.context_today)
    sale_amount = fields.Monetary(string="Sale Proceeds (Excl. Tax)", default=0.0)
    proceeds_account_id = fields.Many2one(
        "account.account",
        string="Bank / Receivable Account",
        help="Account debited for sale proceeds (when selling).",
    )
    loss_gain_account_id = fields.Many2one(
        "account.account",
        string="Gain / Loss on Disposal Account",
        required=True,
    )
    note = fields.Char(string="Reason / Reference")

    def action_confirm_disposal(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.state == "closed":
            raise UserError(_("Asset %s is already closed.") % asset.name)
        journal = asset.journal_id or asset.category_id.journal_id
        asset_acc = asset.category_id.asset_account_id
        depr_acc = asset.depreciation_account_id or asset.category_id.depreciation_account_id
        if not (journal and asset_acc and depr_acc):
            raise UserError(_("Configure Journal, Fixed Asset Account, and Accumulated Depreciation Account on the Asset Category first."))
        if self.disposal_type == "sell" and self.sale_amount > 0 and not self.proceeds_account_id:
            raise UserError(_("Select a Bank / Receivable Account for sale proceeds."))

        # Remove unposted future depreciation lines
        asset.line_ids.filtered(lambda l: not l.move_id).unlink()

        gross = asset.original_value
        accum_depr = asset.depreciated_value
        proceeds = self.sale_amount if self.disposal_type == "sell" else 0.0
        # Gain/loss balancing amount: gross - accum_depr - proceeds (>0 => loss debit, <0 => gain credit)
        net_diff = round(gross - accum_depr - proceeds, 2)

        line_cmds = [
            Command.create({
                "name": f"Disposal Gross Reversal: {asset.name}",
                "account_id": asset_acc.id,
                "debit": 0.0,
                "credit": gross,
            }),
        ]
        if accum_depr > 0:
            line_cmds.append(Command.create({
                "name": f"Accumulated Depreciation Reversal: {asset.name}",
                "account_id": depr_acc.id,
                "debit": accum_depr,
                "credit": 0.0,
            }))
        if proceeds > 0:
            line_cmds.append(Command.create({
                "name": f"Sale Proceeds: {asset.name}",
                "account_id": self.proceeds_account_id.id,
                "debit": proceeds,
                "credit": 0.0,
            }))
        if net_diff != 0.0:
            line_cmds.append(Command.create({
                "name": f"Gain/Loss on Asset Disposal: {asset.name}",
                "account_id": self.loss_gain_account_id.id,
                "debit": net_diff if net_diff > 0 else 0.0,
                "credit": -net_diff if net_diff < 0 else 0.0,
            }))

        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": self.disposal_date,
            "ref": self.note or f"Disposal {asset.code}",
            "company_id": asset.company_id.id,
            "line_ids": line_cmds,
        })
        move.action_post()
        asset.write({
            "state": "closed",
            "disposal_move_id": move.id,
            "disposal_date": self.disposal_date,
            "disposal_proceeds": proceeds,
        })
        asset.message_post(body=_("Asset disposed on %s via journal entry %s.") % (self.disposal_date, move.name))


class CustomAssetModifyWizard(models.TransientModel):
    _name = "custom.asset.modify.wizard"
    _description = "Modify Asset Useful Life / Residual Value"

    asset_id = fields.Many2one("custom.asset", required=True, readonly=True)
    currency_id = fields.Many2one(related="asset_id.currency_id", readonly=True)
    useful_life_months = fields.Integer(string="New Useful Life (Months)", required=True)
    salvage_value = fields.Monetary(string="New Salvage Value", required=True)
    reason = fields.Char(string="Modification Reason")

    def action_apply_modification(self):
        self.ensure_one()
        asset = self.asset_id
        asset.write({
            "useful_life_months": self.useful_life_months,
            "salvage_value": self.salvage_value,
        })
        asset.action_compute_depreciation()
        asset.message_post(body=_("Depreciation schedule modified (%s months, salvage %.2f). Reason: %s") % (
            self.useful_life_months, self.salvage_value, self.reason or "-"
        ))


class AccountMoveLineDeferred(models.Model):
    _inherit = "account.move.line"

    x_deferred_periods = fields.Integer(
        string="Defer Months",
        default=0,
        help="Set > 0 to automatically create a Deferred Revenue (on Invoices) or Prepaid Expense (on Vendor Bills) schedule upon posting.",
    )
    x_deferred_account_id = fields.Many2one(
        "account.account",
        string="Deferred / Prepaid Account",
        help="Balance-sheet Prepaid Expense or Deferred Revenue account.",
    )
    x_generated_deferred_id = fields.Many2one("custom.deferred.schedule", string="Deferred Schedule", readonly=True, copy=False)


class AccountMoveDeferredHook(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        res = super()._post(soft=soft)
        Deferred = self.env["custom.deferred.schedule"]
        for move in self.filtered(lambda m: m.move_type in ("out_invoice", "in_invoice")):
            misc_journal = self.env["account.journal"].search([
                ("company_id", "=", move.company_id.id),
                ("type", "=", "general"),
            ], limit=1)
            for line in move.invoice_line_ids.filtered(
                lambda l: l.x_deferred_periods > 0 and l.x_deferred_account_id and not l.x_generated_deferred_id and l.price_subtotal > 0
            ):
                sched = Deferred.create({
                    "name": f"{move.name} - {line.name}",
                    "schedule_type": "revenue" if move.move_type == "out_invoice" else "expense",
                    "partner_id": move.partner_id.id,
                    "start_date": move.invoice_date or move.date or fields.Date.today(),
                    "periods": line.x_deferred_periods,
                    "total_amount": line.price_subtotal,
                    "journal_id": misc_journal.id if misc_journal else False,
                    "deferred_account_id": line.x_deferred_account_id.id,
                    "recognition_account_id": line.account_id.id,
                    "company_id": move.company_id.id,
                })
                sched.action_generate_lines()
                line.x_generated_deferred_id = sched.id
                move.message_post(body=_("Auto-created Deferred Schedule %s (%s months).") % (sched.name, line.x_deferred_periods))
        return res


class AccountJournalEnterpriseExt(models.Model):
    _inherit = "account.journal"

    def action_open_reconcile_console(self):
        self.ensure_one()
        wiz = self.env["custom.bank.reconcile.wizard"].create({"journal_id": self.id})
        wiz.action_reload_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Reconcile: %s") % self.name,
            "res_model": "custom.bank.reconcile.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_open_bank_import(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Import Statement: %s") % self.name,
            "res_model": "custom.bank.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_journal_id": self.id},
        }


class CustomBankReconcileWizardExt(models.TransientModel):
    _inherit = "custom.bank.reconcile.wizard"

    def action_auto_reconcile_all(self):
        """Automatically match & reconcile all statement lines that have a suggested invoice/bill or matching rule."""
        self.ensure_one()
        rules = self.env["custom.bank.reconcile.rule"].search([("active", "=", True)], order="sequence, id")
        reconciled_count = 0
        for line in self.line_ids.filtered(lambda l: not l.is_reconciled):
            if line.suggested_move_id or line.counterpart_account_id:
                line.action_reconcile_line()
                reconciled_count += 1
                continue
            label = (line.payment_ref or "").lower()
            amt = line.amount
            for rule in rules:
                if rule.transaction_sign == "positive" and amt <= 0:
                    continue
                if rule.transaction_sign == "negative" and amt >= 0:
                    continue
                if rule.match_pattern.lower() in label and rule.account_id:
                    line.counterpart_account_id = rule.account_id.id
                    if rule.partner_id:
                        line.statement_line_id.partner_id = rule.partner_id.id
                    line.action_reconcile_line()
                    reconciled_count += 1
                    break
        return self.action_reload_lines()


class ResConfigSettingsAccountant(models.TransientModel):
    _inherit = "res.config.settings"

    fiscalyear_last_day = fields.Integer(related="company_id.fiscalyear_last_day", readonly=False)
    fiscalyear_last_month = fields.Selection(related="company_id.fiscalyear_last_month", readonly=False)
    fiscalyear_lock_date = fields.Date(related="company_id.fiscalyear_lock_date", readonly=False)
    tax_lock_date = fields.Date(related="company_id.tax_lock_date", readonly=False)
    sale_lock_date = fields.Date(related="company_id.sale_lock_date", readonly=False)
    purchase_lock_date = fields.Date(related="company_id.purchase_lock_date", readonly=False)
    hard_lock_date = fields.Date(related="company_id.hard_lock_date", readonly=False)
