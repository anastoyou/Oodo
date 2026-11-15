from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class CustomBarcodeSession(models.Model):
    _name = "custom.barcode.session"
    _description = "Warehouse Barcode Scan Console"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(string="Session #", readonly=True, copy=False, default="New")
    operation_mode = fields.Selection(
        [
            ("picking", "Validate Transfer (Receipt / Delivery / Internal)"),
            ("inventory", "Instant Stock Cycle Count"),
        ],
        default="picking",
        required=True,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Stock Transfer",
        domain="[('state', 'in', ('assigned', 'confirmed', 'waiting'))]",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Count Location",
        domain="[('usage', '=', 'internal')]",
    )
    scan_input = fields.Char(
        string="Scan Barcode / SKU",
        help="Scan barcode or enter Internal Reference (default_code) and press Enter or click Scan.",
    )
    last_scan_message = fields.Char(readonly=True)
    state = fields.Selection([("draft", "Scanning"), ("applied", "Applied")], default="draft", tracking=True)
    line_ids = fields.One2many("custom.barcode.scan.line", "session_id", string="Scanned Items")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.barcode.session") or "SCAN"
        return super().create(vals_list)

    def _find_product_by_code(self, code):
        cleaned = (code or "").strip()
        if not cleaned:
            return False
        Product = self.env["product.product"]
        return Product.search(["|", ("barcode", "=", cleaned), ("default_code", "=", cleaned)], limit=1)

    @api.onchange("scan_input")
    def _onchange_scan_input(self):
        for session in self:
            if not session.scan_input:
                continue
            code = session.scan_input.strip()
            product = session._find_product_by_code(code)
            if not product:
                session.last_scan_message = _("No product found for barcode/SKU '%s'.") % code
                session.scan_input = False
                return
            existing = session.line_ids.filtered(lambda l: l.product_id == product)[:1]
            if existing:
                existing.scanned_qty += 1.0
            else:
                expected = 0.0
                if session.operation_mode == "picking" and session.picking_id:
                    expected = sum(
                        session.picking_id.move_ids.filtered(lambda m: m.product_id == product).mapped("product_uom_qty")
                    )
                session.line_ids = [
                    Command.create({
                        "product_id": product.id,
                        "scanned_code": code,
                        "expected_qty": expected,
                        "scanned_qty": 1.0,
                    })
                ]
            session.last_scan_message = _("Scanned %s (%s)") % (product.display_name, code)
            session.scan_input = False

    def action_process_scan(self):
        self._onchange_scan_input()

    def action_apply_session(self):
        for session in self:
            if not session.line_ids:
                raise UserError(_("Scan at least one product before applying."))
            if session.operation_mode == "picking":
                if not session.picking_id:
                    raise UserError(_("Select a Stock Transfer to update."))
                for line in session.line_ids:
                    moves = session.picking_id.move_ids.filtered(lambda m: m.product_id == line.product_id)
                    if moves:
                        moves[0].quantity = line.scanned_qty
                session.picking_id.message_post(
                    body=_("Quantities updated via Barcode Scan Session %s.") % session.name
                )
            else:
                if not session.location_id:
                    raise UserError(_("Select an internal Stock Location for cycle counting."))
                Quant = self.env["stock.quant"]
                for line in session.line_ids:
                    quant = Quant.search([
                        ("product_id", "=", line.product_id.id),
                        ("location_id", "=", session.location_id.id),
                    ], limit=1)
                    if not quant:
                        quant = Quant.create({
                            "product_id": line.product_id.id,
                            "location_id": session.location_id.id,
                        })
                    quant.inventory_quantity = line.scanned_qty
                    quant.action_apply_inventory()
            session.state = "applied"


class CustomBarcodeScanLine(models.Model):
    _name = "custom.barcode.scan.line"
    _description = "Barcode Scan Line"
    _order = "id desc"

    session_id = fields.Many2one("custom.barcode.session", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True)
    scanned_code = fields.Char(string="Barcode / SKU")
    expected_qty = fields.Float(string="Expected Qty", readonly=True)
    scanned_qty = fields.Float(string="Scanned Qty", default=1.0)


class CustomQualityPoint(models.Model):
    _name = "custom.quality.point"
    _description = "Quality Control Checkpoint"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    picking_type_code = fields.Selection(
        [("incoming", "Receipts (Vendor / Return)"), ("outgoing", "Deliveries (Dispatch)"), ("internal", "Internal Transfers")],
        default="outgoing",
        required=True,
    )
    product_categ_id = fields.Many2one("product.category", string="Product Category (Optional)")
    check_type = fields.Selection(
        [("pass_fail", "Pass / Fail"), ("measure", "Measurement Range"), ("instructions", "Visual Checklist")],
        default="pass_fail",
        required=True,
    )
    norm_min = fields.Float(string="Min Value", default=0.0)
    norm_max = fields.Float(string="Max Value", default=0.0)
    instructions = fields.Text(string="Inspector Instructions")
    block_picking_validation = fields.Boolean(
        string="Block Transfer Validation Until Passed",
        default=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomQualityCheck(models.Model):
    _name = "custom.quality.check"
    _description = "Quality Control Check"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(string="QC #", readonly=True, copy=False, default="New")
    point_id = fields.Many2one("custom.quality.point", string="Control Point")
    picking_id = fields.Many2one("stock.picking", string="Transfer", ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Product")
    check_type = fields.Selection(
        [("pass_fail", "Pass / Fail"), ("measure", "Measurement Range"), ("instructions", "Visual Checklist")],
        default="pass_fail",
        required=True,
    )
    measure_value = fields.Float(string="Measured Value")
    inspector_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    quality_state = fields.Selection(
        [("none", "To Do"), ("pass", "Passed"), ("fail", "Failed")],
        default="none",
        tracking=True,
    )
    notes = fields.Text(string="Defect / Inspection Notes")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.quality.check") or "QC"
        return super().create(vals_list)

    def action_pass(self):
        for check in self:
            if check.check_type == "measure" and check.point_id:
                if not (check.point_id.norm_min <= check.measure_value <= check.point_id.norm_max):
                    raise UserError(_("Measured value %.2f is outside tolerance [%.2f, %.2f].") % (
                        check.measure_value, check.point_id.norm_min, check.point_id.norm_max
                    ))
            check.quality_state = "pass"
            if check.picking_id and all(c.quality_state == "pass" for c in check.picking_id.x_quality_check_ids):
                check.picking_id.write({"x_qc_verified": True, "x_packing_status": "qc_passed"})

    def action_fail(self):
        self.write({"quality_state": "fail"})


class StockPickingQuality(models.Model):
    _inherit = "stock.picking"

    x_quality_check_ids = fields.One2many("custom.quality.check", "picking_id", string="QC Checks")
    x_quality_check_count = fields.Integer(compute="_compute_x_quality_check_count")

    @api.depends("x_quality_check_ids")
    def _compute_x_quality_check_count(self):
        for picking in self:
            picking.x_quality_check_count = len(picking.x_quality_check_ids)

    def action_generate_quality_checks(self):
        Check = self.env["custom.quality.check"]
        Point = self.env["custom.quality.point"]
        for picking in self:
            if picking.x_quality_check_ids:
                continue
            points = Point.search([
                ("active", "=", True),
                ("picking_type_code", "=", picking.picking_type_code),
            ])
            for point in points:
                matching_moves = picking.move_ids
                if point.product_categ_id:
                    matching_moves = matching_moves.filtered(
                        lambda m: m.product_id.categ_id == point.product_categ_id
                    )
                if not matching_moves:
                    continue
                Check.create({
                    "point_id": point.id,
                    "picking_id": picking.id,
                    "product_id": matching_moves[0].product_id.id,
                    "check_type": point.check_type,
                    "notes": point.instructions,
                })

    def action_view_quality_checks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Quality Checks"),
            "res_model": "custom.quality.check",
            "view_mode": "list,form",
            "domain": [("picking_id", "=", self.id)],
            "context": {"default_picking_id": self.id},
        }

    def button_validate(self):
        for picking in self:
            blocking = picking.x_quality_check_ids.filtered(
                lambda c: c.quality_state != "pass" and (not c.point_id or c.point_id.block_picking_validation)
            )
            if blocking:
                raise UserError(_("Complete and pass all mandatory Quality Control checks before validating %s.") % picking.name)
        return super().button_validate()


class CustomPlmTechpack(models.Model):
    _name = "custom.plm.techpack"
    _description = "Garment / Gadget PLM Tech Pack"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Tech Pack #", readonly=True, copy=False, default="New")
    product_tmpl_id = fields.Many2one("product.template", string="Product", required=True, tracking=True)
    revision = fields.Char(default="v1.0", required=True, tracking=True)
    fabric_gsm = fields.Char(string="Fabric GSM / Material Spec")
    measurement_spec = fields.Text(string="Size / Measurement Chart")
    trim_packaging_notes = fields.Text(string="Trims, Labels & Packaging BOM Notes")
    attachment_data = fields.Binary(string="Tech Pack PDF / CAD", attachment=True)
    attachment_name = fields.Char()
    state = fields.Selection([("draft", "Draft"), ("active", "Production Active"), ("obsolete", "Obsolete")], default="draft", tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.plm.techpack") or "TP"
        return super().create(vals_list)

    def action_activate(self):
        self.write({"state": "active"})


class CustomPlmEco(models.Model):
    _name = "custom.plm.eco"
    _description = "PLM Engineering Change Order (ECO)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="ECO #", readonly=True, copy=False, default="New")
    title = fields.Char(required=True, tracking=True)
    product_tmpl_id = fields.Many2one("product.template", string="Product", required=True)
    techpack_id = fields.Many2one("custom.plm.techpack", string="Target Tech Pack")
    new_revision = fields.Char(string="Target Revision", default="v1.1", required=True)
    change_summary = fields.Text(string="Change Details", required=True)
    stage = fields.Selection(
        [("draft", "New"), ("in_review", "In Review"), ("approved", "Approved"), ("applied", "Applied")],
        default="draft",
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.plm.eco") or "ECO"
        return super().create(vals_list)

    def action_submit_review(self):
        self.write({"stage": "in_review"})

    def action_approve(self):
        self.write({"stage": "approved"})

    def action_apply_changes(self):
        for eco in self:
            if eco.techpack_id:
                eco.techpack_id.write({"revision": eco.new_revision, "state": "active"})
                eco.techpack_id.message_post(body=_("Updated to %s via ECO %s: %s") % (
                    eco.new_revision, eco.name, eco.title
                ))
            eco.stage = "applied"


class CustomMrpMps(models.Model):
    _name = "custom.mrp.mps"
    _description = "Master Production & Replenishment Schedule (MPS)"
    _order = "id desc"

    name = fields.Char(string="Schedule Period", required=True, default=lambda self: f"MPS {fields.Date.today()}")
    product_id = fields.Many2one("product.product", required=True)
    vendor_id = fields.Many2one("res.partner", string="Preferred Supplier")
    forecast_demand = fields.Float(string="Forecasted Demand Qty", required=True, default=50.0)
    safety_stock = fields.Float(string="Safety Stock Target", default=10.0)
    on_hand_qty = fields.Float(related="product_id.qty_available", readonly=True)
    incoming_qty = fields.Float(related="product_id.incoming_qty", readonly=True)
    suggested_replenish_qty = fields.Float(string="Suggested Order Qty", compute="_compute_suggested_qty")
    purchase_order_id = fields.Many2one("purchase.order", string="Generated RFQ", readonly=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.depends("forecast_demand", "safety_stock", "on_hand_qty", "incoming_qty")
    def _compute_suggested_qty(self):
        for rec in self:
            shortfall = (rec.forecast_demand + rec.safety_stock) - (rec.on_hand_qty + rec.incoming_qty)
            rec.suggested_replenish_qty = max(0.0, round(shortfall, 2))

    def action_create_rfq(self):
        self.ensure_one()
        qty = self.suggested_replenish_qty
        if qty <= 0:
            raise UserError(_("Stock on hand plus incoming POs already covers forecast demand + safety stock."))
        vendor = self.vendor_id or (self.product_id.seller_ids[:1].partner_id if self.product_id.seller_ids else False)
        if not vendor:
            raise UserError(_("Select a Preferred Supplier or configure a Vendor Pricelist on the product."))
        po = self.env["purchase.order"].create({
            "partner_id": vendor.id,
            "origin": self.name,
            "order_line": [
                Command.create({
                    "product_id": self.product_id.id,
                    "product_qty": qty,
                })
            ],
        })
        self.purchase_order_id = po.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "res_id": po.id,
            "view_mode": "form",
        }

