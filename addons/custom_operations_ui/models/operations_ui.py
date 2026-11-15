import html
import re
from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class CustomShopfloorWorkorder(models.Model):
    _name = "custom.shopfloor.workorder"
    _description = "Shop Floor / Tailoring & Fulfillment Workcenter Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, id desc"

    name = fields.Char(string="Work Order #", readonly=True, copy=False, default="New")
    title = fields.Char(required=True, tracking=True)
    workcenter = fields.Selection(
        [
            ("cutting", "Cutting & Pattern Bench"),
            ("stitching", "Custom Stitching & Embroidery"),
            ("qc_pressing", "Steam Pressing & QC Check"),
            ("packing", "Dispatch & Gift Packing"),
        ],
        default="stitching",
        required=True,
    )
    priority = fields.Selection([("0", "Normal"), ("1", "Urgent / Express")], default="0")
    product_id = fields.Many2one("product.product", string="Product / SKU")
    sale_order_id = fields.Many2one("sale.order", string="Sales Order")
    operator_id = fields.Many2one("hr.employee", string="Operator / Tailor")
    quantity = fields.Float(default=1.0, required=True)
    instructions = fields.Text(string="Operator Instructions / Measurements")
    stage = fields.Selection(
        [("ready", "Ready"), ("in_progress", "In Progress"), ("paused", "Paused"), ("done", "Completed")],
        default="ready",
        tracking=True,
    )
    timer_started_at = fields.Datetime(readonly=True)
    duration_minutes = fields.Float(string="Elapsed (Minutes)", default=0.0)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.shopfloor.workorder") or "WO"
        return super().create(vals_list)

    def _accumulate_timer(self):
        now = fields.Datetime.now()
        for wo in self:
            if wo.timer_started_at:
                elapsed = max(0.0, (now - wo.timer_started_at).total_seconds() / 60.0)
                wo.duration_minutes = round(wo.duration_minutes + elapsed, 2)
                wo.timer_started_at = False

    def action_start_timer(self):
        for wo in self:
            wo.write({"stage": "in_progress", "timer_started_at": fields.Datetime.now()})

    def action_pause_timer(self):
        self._accumulate_timer()
        self.write({"stage": "paused"})

    def action_complete(self):
        self._accumulate_timer()
        self.write({"stage": "done"})


class CustomTimesheetEntry(models.Model):
    _name = "custom.timesheet.entry"
    _description = "Employee Timesheet & Live Timer"
    _inherit = ["mail.thread"]
    _order = "date desc, id desc"

    name = fields.Char(string="Task / Activity", required=True)
    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    employee_id = fields.Many2one("hr.employee", string="Employee")
    date = fields.Date(required=True, default=fields.Date.context_today)
    sale_order_id = fields.Many2one("sale.order", string="Sales Order")
    field_task_id = fields.Many2one("custom.field.service.task", string="Field Service Task")
    workorder_id = fields.Many2one("custom.shopfloor.workorder", string="Work Order")
    timer_start = fields.Datetime(readonly=True)
    is_running = fields.Boolean(default=False, readonly=True)
    hours_spent = fields.Float(string="Hours", default=0.0)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved")],
        default="draft",
        tracking=True,
    )

    @api.onchange("user_id")
    def _onchange_user_id(self):
        for rec in self:
            if rec.user_id and not rec.employee_id:
                rec.employee_id = rec.user_id.employee_id

    def action_start_timer(self):
        for rec in self:
            if not rec.is_running:
                rec.write({"timer_start": fields.Datetime.now(), "is_running": True})

    def action_stop_timer(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.is_running and rec.timer_start:
                elapsed_hours = max(0.0, (now - rec.timer_start).total_seconds() / 3600.0)
                rec.write({
                    "hours_spent": round(rec.hours_spent + elapsed_hours, 2),
                    "timer_start": False,
                    "is_running": False,
                })

    def action_submit(self):
        self.action_stop_timer()
        self.write({"state": "submitted"})

    def action_approve(self):
        self.action_stop_timer()
        self.write({"state": "approved"})


def _col_to_idx(col_str):
    res = 0
    for ch in col_str.upper():
        res = res * 26 + (ord(ch) - ord("A") + 1)
    return res


def _idx_to_col(idx):
    chars = []
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        chars.append(chr(65 + rem))
    return "".join(reversed(chars))


def _parse_cell_ref(ref):
    m = re.fullmatch(r"([A-Za-z]{1,3})(\d{1,4})", (ref or "").strip().upper())
    if not m:
        return None
    return _col_to_idx(m.group(1)), int(m.group(2))


class CustomSpreadsheetSheet(models.Model):
    _name = "custom.spreadsheet.sheet"
    _description = "Live BI & Financial Formula Spreadsheet"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(required=True)
    code = fields.Char(default="SHEET-1")
    description = fields.Char()
    cell_ids = fields.One2many("custom.spreadsheet.cell", "sheet_id", string="Cells")
    html_preview = fields.Html(string="Live Grid Preview", compute="_compute_html_preview")
    last_recalculated_at = fields.Datetime(readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    def _live_odoo_metrics(self):
        since = fields.Datetime.now() - timedelta(days=30)
        sales_orders = self.env["sale.order"].search([("state", "=", "sale"), ("date_order", ">=", since)])
        sales_30d = round(sum(sales_orders.mapped("amount_total")), 2)
        subs = self.env["custom.subscription"].search([("state", "=", "active")])
        mrr = round(sum(subs.mapped("mrr_amount")), 2)
        open_tickets = float(
            self.env["custom.support.ticket"].search_count([("stage", "in", ("new", "in_progress", "waiting_customer"))])
        )
        quants = self.env["stock.quant"].search([("location_id.usage", "=", "internal")])
        inv_value = round(sum(q.quantity * q.product_id.standard_price for q in quants), 2)
        return {
            "SALES_30D": sales_30d,
            "MRR": mrr,
            "OPEN_TICKETS": open_tickets,
            "INVENTORY_VALUE": inv_value,
        }

    def action_recalculate(self):
        metrics = self._live_odoo_metrics()
        for sheet in self:
            cell_map = {c.cell_ref.upper().strip(): c for c in sheet.cell_ids if c.cell_ref}
            cache = {}

            def eval_cell(ref, visiting):
                ref = ref.upper().strip()
                if ref in cache:
                    return cache[ref]
                if ref in visiting:
                    return 0.0
                cell = cell_map.get(ref)
                if not cell:
                    return 0.0
                raw = (cell.raw_input or "").strip()
                if not raw:
                    cache[ref] = 0.0
                    return 0.0
                if not raw.startswith("="):
                    try:
                        val = float(raw.replace(",", ""))
                        cache[ref] = val
                        return val
                    except ValueError:
                        cache[ref] = raw
                        return raw

                expr = raw[1:].strip()
                visiting = visiting | {ref}

                expr_upper = expr.upper()
                expr_upper = expr_upper.replace("ODOO_SALES_30D()", str(metrics["SALES_30D"]))
                expr_upper = expr_upper.replace("ODOO_MRR()", str(metrics["MRR"]))
                expr_upper = expr_upper.replace("ODOO_OPEN_TICKETS()", str(metrics["OPEN_TICKETS"]))
                expr_upper = expr_upper.replace("ODOO_INVENTORY_VALUE()", str(metrics["INVENTORY_VALUE"]))

                def expand_range(match):
                    fn = match.group(1).upper()
                    c1, r1 = _parse_cell_ref(match.group(2)) or (0, 0)
                    c2, r2 = _parse_cell_ref(match.group(3)) or (0, 0)
                    vals = []
                    for cc in range(min(c1, c2), max(c1, c2) + 1):
                        for rr in range(min(r1, r2), max(r1, r2) + 1):
                            v = eval_cell(f"{_idx_to_col(cc)}{rr}", visiting)
                            if isinstance(v, (int, float)):
                                vals.append(float(v))
                    if not vals:
                        return "0.0"
                    if fn == "SUM":
                        return str(sum(vals))
                    if fn in ("AVG", "AVERAGE"):
                        return str(sum(vals) / len(vals))
                    if fn == "MIN":
                        return str(min(vals))
                    if fn == "MAX":
                        return str(max(vals))
                    if fn == "COUNT":
                        return str(float(len(vals)))
                    return "0.0"

                expr_upper = re.sub(
                    r"\b(SUM|AVERAGE|AVG|MIN|MAX|COUNT)\(\s*([A-Z]{1,3}\d{1,4})\s*:\s*([A-Z]{1,3}\d{1,4})\s*\)",
                    expand_range,
                    expr_upper,
                )

                def replace_ref(match):
                    token = match.group(0)
                    v = eval_cell(token, visiting)
                    return str(float(v)) if isinstance(v, (int, float)) else "0.0"

                expr_upper = re.sub(r"\b[A-Z]{1,3}\d{1,4}\b", replace_ref, expr_upper)

                try:
                    result = safe_eval(expr_upper, {"round": round, "abs": abs, "min": min, "max": max})
                    val = float(result) if isinstance(result, (int, float)) else 0.0
                except Exception:
                    val = 0.0
                cache[ref] = val
                return val

            for ref, cell in cell_map.items():
                val = eval_cell(ref, frozenset())
                if isinstance(val, (int, float)):
                    cell.write({
                        "computed_value": round(float(val), 4),
                        "display_value": f"{round(float(val), 2):,.2f}" if (cell.raw_input or "").strip().startswith("=") or "." in (cell.raw_input or "") else str(round(float(val), 2)).rstrip("0").rstrip("."),
                    })
                else:
                    cell.write({
                        "computed_value": 0.0,
                        "display_value": str(val),
                    })
            sheet.last_recalculated_at = fields.Datetime.now()

    @api.depends("cell_ids.cell_ref", "cell_ids.display_value", "cell_ids.raw_input")
    def _compute_html_preview(self):
        for sheet in self:
            grid = {}
            max_c, max_r = 1, 1
            for cell in sheet.cell_ids:
                parsed = _parse_cell_ref(cell.cell_ref)
                if parsed:
                    c, r = parsed
                    max_c = max(max_c, c)
                    max_r = max(max_r, r)
                    grid[(c, r)] = cell.display_value if cell.display_value is not None else (cell.raw_input or "")
            max_c = min(max_c, 12)
            max_r = min(max_r, 30)
            rows_html = ["<table class='table table-bordered table-sm'><thead><tr><th>#</th>"]
            for c in range(1, max_c + 1):
                rows_html.append(f"<th class='text-center bg-light'>{_idx_to_col(c)}</th>")
            rows_html.append("</tr></thead><tbody>")
            for r in range(1, max_r + 1):
                rows_html.append(f"<tr><th class='bg-light text-center'>{r}</th>")
                for c in range(1, max_c + 1):
                    val = html.escape(str(grid.get((c, r), "")))
                    rows_html.append(f"<td>{val}</td>")
                rows_html.append("</tr>")
            rows_html.append("</tbody></table>")
            sheet.html_preview = "".join(rows_html)


class CustomSpreadsheetCell(models.Model):
    _name = "custom.spreadsheet.cell"
    _description = "Spreadsheet Grid Cell"
    _order = "cell_ref asc"

    sheet_id = fields.Many2one("custom.spreadsheet.sheet", required=True, ondelete="cascade")
    cell_ref = fields.Char(string="Cell (e.g. A1)", required=True)
    raw_input = fields.Char(string="Value or Formula (=...)")
    computed_value = fields.Float(readonly=True)
    display_value = fields.Char(readonly=True)


class CustomStudioAppWizard(models.TransientModel):
    _name = "custom.studio.app.wizard"
    _description = "Studio-Lite Custom Model & Menu Creator"

    app_title = fields.Char(string="App / Record Title", required=True)
    model_technical_name = fields.Char(
        string="Technical Model Name",
        required=True,
        default="x_custom_",
        help="Must start with x_ (e.g. x_custom_fabric_lot).",
    )
    parent_menu_id = fields.Many2one(
        "ir.ui.menu",
        string="Parent Menu",
        required=True,
        default=lambda self: self.env.ref("custom_enterprise.menu_custom_enterprise_ops_root", raise_if_not_found=False),
    )
    include_status_field = fields.Boolean(string="Include Stage / Status Selection", default=True)
    include_notes_field = fields.Boolean(string="Include Multiline Notes Field", default=True)

    def action_create_custom_app(self):
        self.ensure_one()
        mname = (self.model_technical_name or "").strip().lower()
        if not re.fullmatch(r"x_[a-z0-9_]+", mname):
            raise UserError(_("Model technical name must match x_[a-z0-9_]+ (for example x_custom_fabric_lot)."))

        IrModel = self.env["ir.model"].sudo()
        if IrModel.search_count([("model", "=", mname)]):
            raise UserError(_("Model '%s' already exists.") % mname)

        new_model = IrModel.create({
            "name": self.app_title,
            "model": mname,
            "state": "manual",
        })

        IrField = self.env["ir.model.fields"].sudo()
        list_fields = ['<field name="x_name"/>']
        form_fields = ['<field name="x_name"/>']

        if self.include_status_field:
            IrField.create({
                "model_id": new_model.id,
                "name": "x_status",
                "field_description": "Status",
                "ttype": "selection",
                "selection": "[('draft', 'Draft'), ('active', 'Active'), ('done', 'Done')]",
                "state": "manual",
            })
            list_fields.append('<field name="x_status"/>')
            form_fields.append('<field name="x_status"/>')

        if self.include_notes_field:
            IrField.create({
                "model_id": new_model.id,
                "name": "x_notes",
                "field_description": "Notes",
                "ttype": "text",
                "state": "manual",
            })
            form_fields.append('<field name="x_notes"/>')

        self.env["ir.access"].sudo().create({
            "name": f"access_{mname}_user",
            "model_id": new_model.id,
            "group_id": self.env.ref("base.group_user").id,
            "operation": "crud",
        })

        IrView = self.env["ir.ui.view"].sudo()
        IrView.create({
            "name": f"{mname}.list",
            "model": mname,
            "type": "list",
            "arch": f"<list>{''.join(list_fields)}</list>",
        })
        IrView.create({
            "name": f"{mname}.form",
            "model": mname,
            "type": "form",
            "arch": f"<form><sheet><group>{''.join(form_fields)}</group></sheet></form>",
        })

        action = self.env["ir.actions.act_window"].sudo().create({
            "name": self.app_title,
            "res_model": mname,
            "view_mode": "list,form",
        })
        self.env["ir.ui.menu"].sudo().create({
            "name": self.app_title,
            "parent_id": self.parent_menu_id.id,
            "action": f"ir.actions.act_window,{action.id}",
            "sequence": 95,
        })
        return action.read()[0]

