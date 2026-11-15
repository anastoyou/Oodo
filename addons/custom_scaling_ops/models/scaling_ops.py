import base64
import csv
import io
import json
import requests

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class CustomRmaRequest(models.Model):
    _name = "custom.rma.request"
    _description = "Return & Size-Exchange RMA Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="RMA #", readonly=True, copy=False, default="New")
    sale_order_id = fields.Many2one("sale.order", string="Original Order", required=True, tracking=True)
    partner_id = fields.Many2one("res.partner", related="sale_order_id.partner_id", store=True, readonly=True)
    picking_id = fields.Many2one(
        "stock.picking",
        string="Original Delivery",
        domain="[('sale_id', '=', sale_order_id)]",
    )
    request_type = fields.Selection(
        [
            ("size_exchange", "Size / Color Exchange"),
            ("return_refund", "Return & Credit Note Refund"),
            ("rto_restock", "Courier RTO / QC Restock"),
        ],
        default="size_exchange",
        required=True,
        tracking=True,
    )
    reason = fields.Selection(
        [
            ("size_small", "Size Too Small"),
            ("size_large", "Size Too Large"),
            ("defective", "Damaged / Stitching Defect"),
            ("wrong_item", "Wrong SKU Delivered"),
            ("color_mismatch", "Color / Fabric Mismatch"),
            ("rto", "Customer Refused / RTO"),
        ],
        default="size_small",
        required=True,
    )
    state = fields.Selection(
        [
            ("draft", "New"),
            ("approved", "Pickup / Return Scheduled"),
            ("received", "QC Inspected & Received"),
            ("done", "Completed"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many("custom.rma.line", "rma_id", string="Items to Return / Exchange")
    return_picking_id = fields.Many2one("stock.picking", string="Return Receipt", readonly=True, copy=False)
    exchange_order_id = fields.Many2one("sale.order", string="Replacement Order", readonly=True, copy=False)
    credit_note_id = fields.Many2one("account.move", string="Credit Note", readonly=True, copy=False)
    notes = fields.Text()
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.rma.request") or "RMA"
        return super().create(vals_list)

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        for rma in self:
            if rma.sale_order_id and not rma.line_ids:
                rma.line_ids = [
                    Command.create({
                        "product_id": line.product_id.id,
                        "exchange_product_id": line.product_id.id,
                        "quantity": line.product_uom_qty,
                        "price_unit": line.price_unit,
                    })
                    for line in rma.sale_order_id.order_line
                    if line.product_id and line.product_id.type != "service"
                ]

    def action_create_return_picking(self):
        Picking = self.env["stock.picking"]
        PickingType = self.env["stock.picking.type"]
        cust_loc = self.env.ref("stock.stock_location_customers", raise_if_not_found=False)
        for rma in self:
            if rma.return_picking_id:
                continue
            if not rma.line_ids:
                raise UserError(_("Add at least one item before creating a return receipt."))
            in_type = PickingType.search(
                [("code", "=", "incoming"), ("warehouse_id.company_id", "=", rma.company_id.id)], limit=1
            )
            if not in_type:
                raise UserError(_("No incoming receipt operation type found for company %s.") % rma.company_id.name)
            dest_loc = in_type.default_location_dest_id
            src_loc = cust_loc or in_type.default_location_src_id or dest_loc
            picking = Picking.create({
                "partner_id": rma.partner_id.id,
                "picking_type_id": in_type.id,
                "location_id": src_loc.id,
                "location_dest_id": dest_loc.id,
                "origin": f"{rma.name} ({rma.sale_order_id.name})",
                "x_dispatch_note": f"RMA Return: {rma.reason}",
                "move_ids": [
                    Command.create({
                        "product_id": l.product_id.id,
                        "uom_id": l.product_id.uom_id.id,
                        "product_uom_qty": l.quantity,
                        "location_id": src_loc.id,
                        "location_dest_id": dest_loc.id,
                        "description_picking": l.product_id.display_name,
                    })
                    for l in rma.line_ids
                ],
            })
            picking.action_confirm()
            rma.write({"return_picking_id": picking.id, "state": "approved"})
            rma.message_post(body=_("Created Return Receipt %s.") % picking.name)

    def action_mark_received(self):
        self.write({"state": "received"})

    def action_create_exchange_order(self):
        SaleOrder = self.env["sale.order"]
        for rma in self:
            if rma.exchange_order_id:
                continue
            if not rma.line_ids:
                raise UserError(_("Add items before creating an exchange order."))
            exch_so = SaleOrder.create({
                "partner_id": rma.partner_id.id,
                "client_order_ref": f"EXCH-{rma.name}",
                "x_sales_channel": rma.sale_order_id.x_sales_channel or "website",
                "x_payment_mode": "prepaid",
                "order_line": [
                    Command.create({
                        "product_id": (l.exchange_product_id or l.product_id).id,
                        "product_uom_qty": l.quantity,
                        "price_unit": 0.0,
                        "name": f"Free Size Exchange ({rma.name}): {(l.exchange_product_id or l.product_id).display_name}",
                    })
                    for l in rma.line_ids
                ],
            })
            rma.write({"exchange_order_id": exch_so.id, "state": "done"})
            rma.message_post(body=_("Created Replacement Exchange Order %s.") % exch_so.name)

    def action_create_credit_note(self):
        Move = self.env["account.move"]
        for rma in self:
            if rma.credit_note_id:
                continue
            if not rma.line_ids:
                raise UserError(_("Add items before issuing a credit note."))
            cn = Move.create({
                "move_type": "out_refund",
                "partner_id": rma.partner_id.id,
                "invoice_origin": f"{rma.name} / {rma.sale_order_id.name}",
                "invoice_line_ids": [
                    Command.create({
                        "product_id": l.product_id.id,
                        "name": f"RMA Refund ({rma.name}): {l.product_id.display_name}",
                        "quantity": l.quantity,
                        "price_unit": l.price_unit,
                    })
                    for l in rma.line_ids
                ],
            })
            rma.write({"credit_note_id": cn.id, "state": "done"})
            rma.message_post(body=_("Created Draft Credit Note for RMA %s.") % rma.name)


class CustomRmaLine(models.Model):
    _name = "custom.rma.line"
    _description = "RMA Item Line"

    rma_id = fields.Many2one("custom.rma.request", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Returned Variant", required=True)
    exchange_product_id = fields.Many2one("product.product", string="Replacement Variant")
    quantity = fields.Float(default=1.0, required=True)
    price_unit = fields.Float(string="Unit Price", default=0.0)


class CustomCourierConfig(models.Model):
    _name = "custom.courier.config"
    _description = "Indian Courier Aggregator Config (Shiprocket / Delhivery)"

    name = fields.Char(required=True)
    provider = fields.Selection(
        [("shiprocket", "Shiprocket API"), ("delhivery", "Delhivery One API"), ("custom", "Custom Carrier / Local")],
        default="shiprocket",
        required=True,
    )
    active = fields.Boolean(default=True)
    sandbox_mode = fields.Boolean(string="Sandbox Simulation Mode", default=True)
    api_email = fields.Char(string="API Email / Client ID")
    api_token = fields.Char(string="API Secret / Token")
    pickup_location_name = fields.Char(string="Warehouse Pickup Location Code", default="Surat_HQ")
    webhook_secret = fields.Char(default="zoee_courier_2026")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomCourierPincodeRule(models.Model):
    _name = "custom.courier.pincode.rule"
    _description = "COD Pincode Blocklist & Courier SLA"
    _order = "pincode asc"

    pincode = fields.Char(string="6-Digit Pincode", required=True, index=True)
    city = fields.Char()
    state_name = fields.Char()
    allow_cod = fields.Boolean(string="Allow Cash on Delivery", default=True)
    is_serviceable = fields.Boolean(default=True)
    risk_note = fields.Char(string="High-RTO / Zone Note")


class StockPickingCourier(models.Model):
    _inherit = "stock.picking"

    x_courier_config_id = fields.Many2one("custom.courier.config", string="Courier Aggregator")
    x_awb_number = fields.Char(string="AWB / Waybill #", copy=False, tracking=True)
    x_courier_status = fields.Selection(
        [
            ("pending", "Awaiting Manifest"),
            ("manifested", "AWB Assigned / Manifested"),
            ("in_transit", "In Transit"),
            ("out_for_delivery", "Out for Delivery"),
            ("delivered", "Delivered"),
            ("rto_initiated", "RTO Initiated"),
            ("rto_delivered", "RTO Received"),
        ],
        default="pending",
        tracking=True,
    )
    x_courier_label_url = fields.Char(string="Label / Tracking URL", copy=False)

    def action_generate_awb(self):
        cfg_default = self.env["custom.courier.config"].search([("active", "=", True)], limit=1)
        for picking in self:
            cfg = picking.x_courier_config_id or cfg_default
            if not cfg:
                raise UserError(_("Configure an active Courier Aggregator first."))

            if cfg.sandbox_mode or not cfg.api_token:
                prefix = "SR" if cfg.provider == "shiprocket" else ("DLV" if cfg.provider == "delhivery" else "AWB")
                awb = f"{prefix}-{picking.id:06d}"
                label_url = f"https://track.local/awb/{awb}"
            elif cfg.provider == "shiprocket":
                headers = {"Authorization": f"Bearer {cfg.api_token}", "Content-Type": "application/json"}
                payload = {
                    "order_id": picking.origin or picking.name,
                    "pickup_location": cfg.pickup_location_name or "Primary",
                    "billing_customer_name": picking.partner_id.name or "Customer",
                    "billing_address": picking.partner_id.street or "Surat",
                    "billing_city": picking.partner_id.city or "Surat",
                    "billing_pincode": picking.partner_id.zip or "395001",
                    "billing_phone": picking.partner_id.phone or "9999999999",
                    "payment_method": "Prepaid",
                    "sub_total": sum(m.product_id.lst_price * m.product_uom_qty for m in picking.move_ids) or 100.0,
                }
                resp = requests.post(
                    "https://apiv2.shiprocket.in/v1/external/orders/create/adhoc",
                    json=payload,
                    headers=headers,
                    timeout=12,
                )
                data = resp.json() if resp.content else {}
                if not resp.ok:
                    raise UserError(_("Shiprocket API error: %s") % data)
                awb = str(data.get("awb_code") or data.get("shipment_id") or f"SR-{picking.id}")
                label_url = data.get("label_url") or ""
            else:
                awb = f"DLV-{picking.id:06d}"
                label_url = ""

            vals = {
                "x_courier_config_id": cfg.id,
                "x_awb_number": awb,
                "x_courier_status": "manifested",
                "x_courier_label_url": label_url,
                "x_packing_status": "packed",
            }
            if hasattr(picking, "carrier_tracking_ref"):
                vals["carrier_tracking_ref"] = awb
            picking.write(vals)
            picking.message_post(body=_("Courier AWB generated via %s: %s") % (cfg.name, awb))


class CustomMarketplaceChannel(models.Model):
    _name = "custom.marketplace.channel"
    _description = "Indian Marketplace Catalog & Sync Config"

    name = fields.Char(required=True)
    channel_code = fields.Selection(
        [
            ("marketplace_myntra", "Myntra"),
            ("marketplace_ajio", "Ajio"),
            ("marketplace_amazon", "Amazon India"),
            ("marketplace_flipkart", "Flipkart"),
            ("marketplace_meesho", "Meesho"),
        ],
        required=True,
    )
    active = fields.Boolean(default=True)
    default_pricelist_multiplier = fields.Float(string="Marketplace Markup Factor", default=1.0)
    last_export_at = fields.Datetime(readonly=True)
    exported_csv = fields.Binary(string="Catalog Feed CSV", readonly=True, attachment=True)
    exported_filename = fields.Char(readonly=True)

    def action_export_catalog_csv(self):
        for ch in self:
            products = self.env["product.product"].search([("sale_ok", "=", True)], limit=500)
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["SKU", "Barcode", "ProductName", "Category", "MRP", "ChannelPrice", "StockQty", "Fabric", "Fit"])
            factor = ch.default_pricelist_multiplier or 1.0
            for p in products:
                writer.writerow([
                    p.default_code or f"SKU-{p.id}",
                    p.barcode or "",
                    p.display_name,
                    p.categ_id.complete_name,
                    round(p.lst_price, 2),
                    round(p.lst_price * factor, 2),
                    p.qty_available,
                    p.product_tmpl_id.x_fabric or "",
                    p.product_tmpl_id.x_fit_type or "",
                ])
            csv_b64 = base64.b64encode(buf.getvalue().encode("utf-8")).decode("ascii")
            ch.write({
                "exported_csv": csv_b64,
                "exported_filename": f"{ch.channel_code}_catalog_feed.csv",
                "last_export_at": fields.Datetime.now(),
            })


class CustomMarketplaceImportWizard(models.TransientModel):
    _name = "custom.marketplace.import.wizard"
    _description = "Marketplace Order CSV Importer"

    channel_id = fields.Many2one("custom.marketplace.channel", required=True)
    csv_file = fields.Binary(string="Upload Order CSV")
    csv_text = fields.Text(
        string="Or Paste CSV Rows",
        default="OrderNo,CustomerName,Phone,SKU,Qty,UnitPrice,PaymentMode\n",
    )
    auto_confirm = fields.Boolean(string="Auto-Confirm Imported Orders", default=True)
    imported_count = fields.Integer(readonly=True)

    def action_import_orders(self):
        self.ensure_one()
        raw_csv = self.csv_text or ""
        if self.csv_file:
            raw_bytes = self.csv_file.content if hasattr(self.csv_file, "content") else base64.b64decode(self.csv_file)
            raw_csv = raw_bytes.decode("utf-8", errors="ignore")

        reader = csv.DictReader(io.StringIO(raw_csv.strip()))
        Partner = self.env["res.partner"]
        Product = self.env["product.product"]
        SaleOrder = self.env["sale.order"]

        grouped = {}
        for row in reader:
            ord_no = (row.get("OrderNo") or "").strip()
            sku = (row.get("SKU") or "").strip()
            if not ord_no or not sku:
                continue
            grouped.setdefault(ord_no, []).append(row)

        created = 0
        for ord_no, rows in grouped.items():
            if SaleOrder.search_count([("client_order_ref", "=", ord_no)]):
                continue
            first = rows[0]
            cname = (first.get("CustomerName") or f"Marketplace Customer ({ord_no})").strip()
            phone = (first.get("Phone") or "").strip()
            partner = Partner.search([("phone", "=", phone)], limit=1) if phone else False
            if not partner:
                partner = Partner.create({"name": cname, "phone": phone})

            lines = []
            for r in rows:
                sku = (r.get("SKU") or "").strip()
                prod = Product.search(["|", ("default_code", "=", sku), ("barcode", "=", sku)], limit=1)
                if not prod:
                    continue
                qty = float(r.get("Qty") or 1.0)
                price = float(r.get("UnitPrice") or prod.lst_price or 0.0)
                lines.append(Command.create({"product_id": prod.id, "product_uom_qty": qty, "price_unit": price}))

            if not lines:
                continue
            pmode = "cod" if "cod" in (first.get("PaymentMode") or "").lower() else "prepaid"
            so = SaleOrder.create({
                "partner_id": partner.id,
                "client_order_ref": ord_no,
                "x_sales_channel": self.channel_id.channel_code,
                "x_payment_mode": pmode,
                "order_line": lines,
            })
            if self.auto_confirm:
                so.action_confirm()
            created += 1

        self.imported_count = created
        return {
            "type": "ir.actions.act_window",
            "name": _("Marketplace Orders Imported"),
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("x_sales_channel", "=", self.channel_id.channel_code)],
        }


class CustomWarrantyClaim(models.Model):
    _name = "custom.warranty.claim"
    _description = "Gadget & Product Warranty Repair Claim"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Claim #", readonly=True, copy=False, default="New")
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    product_id = fields.Many2one("product.product", string="Product / Device", required=True)
    serial_imei = fields.Char(string="Serial / IMEI #", required=True)
    sale_order_id = fields.Many2one("sale.order", string="Original Sale")
    claim_type = fields.Selection(
        [("repair", "Warranty Repair"), ("replace", "1-to-1 Replacement"), ("doa", "Dead on Arrival (DOA)")],
        default="repair",
        required=True,
    )
    issue_description = fields.Text(required=True)
    resolution_notes = fields.Text()
    state = fields.Selection(
        [("new", "New Claim"), ("diagnosing", "In Inspection"), ("resolved", "Repaired / Replaced"), ("closed", "Closed")],
        default="new",
        tracking=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.warranty.claim") or "WRN"
        return super().create(vals_list)

    def action_diagnose(self):
        self.write({"state": "diagnosing"})

    def action_resolve(self):
        self.write({"state": "resolved"})

    def action_close(self):
        self.write({"state": "closed"})


class CustomIntercompanyRule(models.Model):
    _name = "custom.intercompany.rule"
    _description = "Franchise & Multi-Company PO -> SO Sync Rule"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    buyer_company_id = fields.Many2one("res.company", string="Buyer / Franchise Company", required=True)
    supplier_company_id = fields.Many2one("res.company", string="Supplying Hub Company", required=True)
    supplier_partner_id = fields.Many2one("res.partner", string="Supplier Partner (on Buyer PO)", required=True)
    buyer_customer_id = fields.Many2one("res.partner", string="Franchise Customer (on Hub SO)", required=True)
    auto_confirm_so = fields.Boolean(string="Auto-Confirm Hub Sales Order", default=True)


class PurchaseOrderIntercompany(models.Model):
    _inherit = "purchase.order"

    x_intercompany_so_id = fields.Many2one("sale.order", string="Mirrored Inter-Company SO", readonly=True, copy=False)

    def button_confirm(self):
        res = super().button_confirm()
        Rule = self.env["custom.intercompany.rule"].sudo()
        for po in self:
            if po.x_intercompany_so_id:
                continue
            rule = Rule.search([
                ("active", "=", True),
                ("buyer_company_id", "=", po.company_id.id),
                ("supplier_partner_id", "=", po.partner_id.id),
            ], limit=1)
            if not rule:
                continue
            so_env = self.env["sale.order"].sudo().with_company(rule.supplier_company_id)
            mirror_so = so_env.create({
                "partner_id": rule.buyer_customer_id.id,
                "company_id": rule.supplier_company_id.id,
                "client_order_ref": po.name,
                "x_sales_channel": "b2b_wholesale",
                "order_line": [
                    Command.create({
                        "product_id": l.product_id.id,
                        "product_uom_qty": l.product_qty,
                        "price_unit": l.price_unit,
                    })
                    for l in po.order_line
                    if l.product_id
                ],
            })
            if rule.auto_confirm_so:
                mirror_so.action_confirm()
            po.x_intercompany_so_id = mirror_so.id
            po.message_post(body=_("Auto-created Inter-Company Sales Order %s in %s.") % (mirror_so.name, rule.supplier_company_id.name))
        return res


class SaleOrderRmaLink(models.Model):
    _inherit = "sale.order"

    def action_create_rma(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Return / Size Exchange RMA"),
            "res_model": "custom.rma.request",
            "view_mode": "form",
            "context": {
                "default_sale_order_id": self.id,
                "default_line_ids": [
                    Command.create({
                        "product_id": l.product_id.id,
                        "exchange_product_id": l.product_id.id,
                        "quantity": l.product_uom_qty,
                        "price_unit": l.price_unit,
                    })
                    for l in self.order_line
                    if l.product_id and l.product_id.type != "service"
                ],
            },
        }

