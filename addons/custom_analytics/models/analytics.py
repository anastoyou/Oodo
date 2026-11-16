import json
from datetime import timedelta

from odoo import Command, _, api, fields, models


class CustomAnalyticsBoard(models.TransientModel):
    _name = "custom.analytics.board"
    _description = "Live Cross-ERP Analytics Console"

    @api.model
    def _get_channel_selection(self):
        return list(self.env["sale.order"]._fields["x_sales_channel"].selection)

    # Interactive Filters
    date_from = fields.Date(default=lambda self: fields.Date.today() - timedelta(days=30), required=True)
    date_to = fields.Date(default=fields.Date.context_today, required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer Filter")
    sales_channel = fields.Selection(selection="_get_channel_selection", string="Channel Filter")
    payment_mode = fields.Selection(
        [("prepaid", "Prepaid"), ("cod", "Cash on Delivery")],
        string="Payment Filter",
    )
    active_module = fields.Selection(
        [
            ("all", "All Modules (360° View)"),
            ("sales_crm", "Sales, Channels & CRM"),
            ("purchase_stock", "Purchase, Vendors & Inventory"),
            ("finance", "Finance, Invoices & Cashflow"),
            ("ops_hr", "Operations, HR, RMA & Support"),
        ],
        string="Module Focus",
        default="all",
        required=True,
    )

    # Sales, Margin & Risk + Period-over-Period Comparison
    total_sales = fields.Monetary(readonly=True)
    prev_total_sales = fields.Monetary(string="Prev. Period Sales", readonly=True)
    sales_growth_pct = fields.Float(string="Sales vs Prev. %", readonly=True)
    total_margin = fields.Monetary(readonly=True)
    prev_total_margin = fields.Monetary(string="Prev. Period Margin", readonly=True)
    margin_growth_pct = fields.Float(string="Margin vs Prev. %", readonly=True)
    margin_pct = fields.Float(string="Margin %", readonly=True)
    order_count = fields.Integer(readonly=True)
    prev_order_count = fields.Integer(string="Prev. Period Orders", readonly=True)
    orders_growth_pct = fields.Float(string="Orders vs Prev. %", readonly=True)
    prepaid_order_count = fields.Integer(readonly=True)
    cod_order_count = fields.Integer(readonly=True)
    rto_order_count = fields.Integer(readonly=True)
    rto_rate_pct = fields.Float(string="RTO Rate %", readonly=True)

    # Purchasing & Inventory
    purchase_spend = fields.Monetary(string="Confirmed Purchase Spend", readonly=True)
    prev_purchase_spend = fields.Monetary(string="Prev. Period Spend", readonly=True)
    purchase_growth_pct = fields.Float(string="Spend vs Prev. %", readonly=True)
    purchase_count = fields.Integer(string="Confirmed POs", readonly=True)
    inventory_value = fields.Monetary(string="Stock Valuation (Cost)", readonly=True)
    low_stock_count = fields.Integer(string="Low Stock SKUs (<=5)", readonly=True)

    # Finance & CRM
    invoiced_revenue = fields.Monetary(string="Posted Customer Invoices", readonly=True)
    vendor_bills_total = fields.Monetary(string="Posted Vendor Bills", readonly=True)
    customer_receivable = fields.Monetary(string="Open Receivables", readonly=True)
    vendor_payable = fields.Monetary(string="Open Payables", readonly=True)
    crm_pipeline_value = fields.Monetary(string="Open CRM Pipeline", readonly=True)
    crm_open_count = fields.Integer(string="Open CRM Leads", readonly=True)

    # Operations, Subscriptions, HR & Support
    active_mrr = fields.Monetary(string="Active Subscription MRR", readonly=True)
    active_rental_total = fields.Monetary(string="Rental Revenue", readonly=True)
    payroll_total = fields.Monetary(string="Payroll Spend (Net)", readonly=True)
    timesheet_hours = fields.Float(string="Logged Timesheet Hours", readonly=True)
    open_rma_count = fields.Integer(string="Open RMAs", readonly=True)
    open_ticket_count = fields.Integer(string="Open Support Tickets", readonly=True)

    channel_line_ids = fields.One2many("custom.analytics.channel.line", "board_id", string="Channel Breakdown")
    customer_line_ids = fields.One2many("custom.analytics.customer.line", "board_id", string="Top Customers")
    product_line_ids = fields.One2many("custom.analytics.product.line", "board_id", string="Top Products")
    vendor_line_ids = fields.One2many("custom.analytics.vendor.line", "board_id", string="Top Vendors")
    stock_line_ids = fields.One2many("custom.analytics.stock.line", "board_id", string="Stock & Low-Stock Watch")
    trend_line_ids = fields.One2many("custom.analytics.trend.line", "board_id", string="Daily Sales vs Purchase")

    @api.model
    def _calc_growth_pct(self, current, previous):
        if not previous:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100.0, 1)

    @api.model
    def _build_sale_domain(self, company, d_from, d_to, partner=None, sales_channel=None, payment_mode=None):
        dt_from = fields.Datetime.to_datetime(d_from)
        dt_to = fields.Datetime.to_datetime(d_to) + timedelta(days=1)
        domain = [
            ("company_id", "=", company.id),
            ("state", "=", "sale"),
            ("date_order", ">=", dt_from),
            ("date_order", "<", dt_to),
        ]
        if partner:
            domain.append(("partner_id", "=", partner.id))
        if sales_channel:
            domain.append(("x_sales_channel", "=", sales_channel))
        if payment_mode:
            domain.append(("x_payment_mode", "=", payment_mode))
        return domain

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        metrics = self._compute_period_metrics(
            fields.Date.today() - timedelta(days=30),
            fields.Date.today(),
            self.env.company,
        )
        res.update(metrics)
        return res

    def _compute_sales_metrics(self, orders, prev_orders):
        total_sales = round(sum(orders.mapped("amount_total")), 2)
        prev_sales = round(sum(prev_orders.mapped("amount_total")), 2)
        total_margin = round(sum(orders.mapped("margin")), 2) if "margin" in orders._fields else 0.0
        prev_margin = round(sum(prev_orders.mapped("margin")), 2) if "margin" in prev_orders._fields else 0.0
        order_count = len(orders)
        prev_count = len(prev_orders)
        cod_count = len(orders.filtered(lambda o: o.x_payment_mode == "cod"))
        prepaid_count = order_count - cod_count
        rto_count = len(orders.filtered(lambda o: o.x_is_rto))

        channel_labels = dict(self.env["sale.order"]._fields["x_sales_channel"].selection)
        grouped = {}
        cust_map = {}
        for o in orders:
            key = o.x_sales_channel or "website"
            bucket = grouped.setdefault(key, {"orders": 0, "revenue": 0.0, "cod": 0, "rto": 0})
            bucket["orders"] += 1
            bucket["revenue"] += o.amount_total
            if o.x_payment_mode == "cod":
                bucket["cod"] += 1
            if o.x_is_rto:
                bucket["rto"] += 1

            if o.partner_id:
                cb = cust_map.setdefault(o.partner_id.id, {"orders": 0, "revenue": 0.0, "cod": 0})
                cb["orders"] += 1
                cb["revenue"] += o.amount_total
                if o.x_payment_mode == "cod":
                    cb["cod"] += 1

        max_rev = max((v["revenue"] for v in grouped.values()), default=0.0)
        ch_lines = [
            Command.create({
                "channel_name": channel_labels.get(k, k),
                "order_count": v["orders"],
                "revenue": round(v["revenue"], 2),
                "share_pct": round((v["revenue"] / total_sales * 100.0), 1) if total_sales else 0.0,
                "bar_pct": round((v["revenue"] / max_rev * 100.0), 1) if max_rev else 0.0,
                "cod_count": v["cod"],
                "rto_count": v["rto"],
            })
            for k, v in sorted(grouped.items(), key=lambda kv: kv[1]["revenue"], reverse=True)
        ]

        cust_lines = [
            Command.create({
                "partner_id": pid,
                "order_count": v["orders"],
                "revenue": round(v["revenue"], 2),
                "share_pct": round((v["revenue"] / total_sales * 100.0), 1) if total_sales else 0.0,
                "cod_count": v["cod"],
            })
            for pid, v in sorted(cust_map.items(), key=lambda kv: kv[1]["revenue"], reverse=True)[:15]
        ]

        prod_map = {}
        for line in orders.mapped("order_line"):
            if not line.product_id:
                continue
            bucket = prod_map.setdefault(line.product_id.id, {"qty": 0.0, "rev": 0.0})
            bucket["qty"] += line.product_uom_qty
            bucket["rev"] += line.price_subtotal

        prod_lines = [
            Command.create({
                "product_id": pid,
                "units_sold": round(v["qty"], 2),
                "revenue": round(v["rev"], 2),
            })
            for pid, v in sorted(prod_map.items(), key=lambda kv: kv[1]["rev"], reverse=True)[:15]
        ]

        return {
            "total_sales": total_sales,
            "prev_total_sales": prev_sales,
            "sales_growth_pct": self._calc_growth_pct(total_sales, prev_sales),
            "total_margin": total_margin,
            "prev_total_margin": prev_margin,
            "margin_growth_pct": self._calc_growth_pct(total_margin, prev_margin),
            "margin_pct": round((total_margin / total_sales * 100.0), 2) if total_sales else 0.0,
            "order_count": order_count,
            "prev_order_count": prev_count,
            "orders_growth_pct": self._calc_growth_pct(order_count, prev_count),
            "prepaid_order_count": prepaid_count,
            "cod_order_count": cod_count,
            "rto_order_count": rto_count,
            "rto_rate_pct": round((rto_count / order_count * 100.0), 2) if order_count else 0.0,
            "channel_line_ids": ch_lines,
            "customer_line_ids": cust_lines,
            "product_line_ids": prod_lines,
        }

    def _compute_purchase_metrics(self, pos, prev_pos):
        spend = round(sum(pos.mapped("amount_total")), 2)
        prev_spend = round(sum(prev_pos.mapped("amount_total")), 2)
        vendor_map = {}
        for po in pos:
            if not po.partner_id:
                continue
            bucket = vendor_map.setdefault(po.partner_id.id, {"count": 0, "spend": 0.0})
            bucket["count"] += 1
            bucket["spend"] += po.amount_total

        vendor_lines = [
            Command.create({
                "partner_id": pid,
                "po_count": v["count"],
                "total_spend": round(v["spend"], 2),
            })
            for pid, v in sorted(vendor_map.items(), key=lambda kv: kv[1]["spend"], reverse=True)[:15]
        ]
        return {
            "purchase_spend": spend,
            "prev_purchase_spend": prev_spend,
            "purchase_growth_pct": self._calc_growth_pct(spend, prev_spend),
            "purchase_count": len(pos),
            "vendor_line_ids": vendor_lines,
        }

    def _compute_stock_metrics(self, company):
        quants = self.env["stock.quant"].search([
            ("company_id", "=", company.id),
            ("location_id.usage", "=", "internal"),
        ])
        prod_stock = {}
        for q in quants:
            if not q.product_id:
                continue
            b = prod_stock.setdefault(q.product_id.id, {
                "qty": 0.0,
                "res": 0.0,
                "cost": q.product_id.standard_price,
            })
            b["qty"] += q.quantity
            b["res"] += q.reserved_quantity

        total_val = 0.0
        low_count = 0
        rows = []
        for pid, v in prod_stock.items():
            avail = v["qty"] - v["res"]
            val = round(v["qty"] * v["cost"], 2)
            total_val += val
            is_low = avail <= 5.0
            if is_low:
                low_count += 1
            rows.append((pid, v["qty"], v["res"], avail, val, is_low))

        rows.sort(key=lambda r: (not r[5], -r[4]))
        stock_lines = [
            Command.create({
                "product_id": pid,
                "qty_on_hand": round(qty, 2),
                "qty_reserved": round(res, 2),
                "qty_available": round(avail, 2),
                "stock_value": val,
                "is_low_stock": is_low,
            })
            for pid, qty, res, avail, val, is_low in rows[:20]
        ]
        return {
            "inventory_value": round(total_val, 2),
            "low_stock_count": low_count,
            "stock_line_ids": stock_lines,
        }

    def _compute_finance_crm_ops_metrics(self, date_from, date_to, company, partner=None):
        Move = self.env["account.move"]
        partner_clause = [("partner_id", "=", partner.id)] if partner else []

        cust_inv = Move.search([
            ("company_id", "=", company.id),
            ("state", "=", "posted"),
            ("move_type", "=", "out_invoice"),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
        ] + partner_clause)
        vend_bills = Move.search([
            ("company_id", "=", company.id),
            ("state", "=", "posted"),
            ("move_type", "=", "in_invoice"),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
        ])
        open_ar = Move.search([
            ("company_id", "=", company.id),
            ("state", "=", "posted"),
            ("move_type", "=", "out_invoice"),
            ("amount_residual", ">", 0),
        ] + partner_clause)
        open_ap = Move.search([
            ("company_id", "=", company.id),
            ("state", "=", "posted"),
            ("move_type", "=", "in_invoice"),
            ("amount_residual", ">", 0),
        ])
        leads = self.env["crm.lead"].search([
            ("company_id", "=", company.id),
            ("stage_id.is_won", "=", False),
            ("active", "=", True),
        ] + partner_clause)
        subs = self.env["custom.subscription"].search([
            ("company_id", "=", company.id),
            ("state", "=", "active"),
        ] + partner_clause)
        rentals = self.env["custom.rental.order"].search([
            ("company_id", "=", company.id),
            ("state", "in", ("confirmed", "picked_up", "returned")),
        ] + partner_clause)
        payslips = self.env["custom.hr.payslip"].search([
            ("company_id", "=", company.id),
            ("date_from", ">=", date_from),
            ("date_to", "<=", date_to),
            ("state", "in", ("done", "paid")),
        ])
        timesheets = self.env["custom.timesheet.entry"].search([
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ])

        return {
            "invoiced_revenue": round(sum(cust_inv.mapped("amount_total")), 2),
            "vendor_bills_total": round(sum(vend_bills.mapped("amount_total")), 2),
            "customer_receivable": round(sum(open_ar.mapped("amount_residual")), 2),
            "vendor_payable": round(sum(open_ap.mapped("amount_residual")), 2),
            "crm_pipeline_value": round(sum(leads.mapped("expected_revenue")), 2),
            "crm_open_count": len(leads),
            "active_mrr": round(sum(subs.mapped("mrr_amount")), 2),
            "active_rental_total": round(sum(rentals.mapped("total_payable")), 2),
            "payroll_total": round(sum(payslips.mapped("net_wage")), 2),
            "timesheet_hours": round(sum(timesheets.mapped("hours_spent")), 2),
            "open_rma_count": self.env["custom.rma.request"].search_count([("state", "in", ("draft", "approved", "received"))] + partner_clause),
            "open_ticket_count": self.env["custom.support.ticket"].search_count([("stage", "in", ("new", "in_progress", "waiting_customer"))] + partner_clause),
        }

    def _compute_trend_lines(self, date_from, date_to, prev_from, orders, prev_orders, pos):
        span_days = max(1, (date_to - date_from).days + 1)
        display_span = min(14, span_days)
        start_day = date_to - timedelta(days=display_span - 1)
        offset = (date_from - prev_from).days

        daily = {}
        for i in range(display_span):
            day = start_day + timedelta(days=i)
            daily[day] = {"sales": 0.0, "prev_sales": 0.0, "purchase": 0.0, "orders": 0}

        for o in orders:
            day = fields.Date.to_date(o.date_order)
            if day in daily:
                daily[day]["sales"] += o.amount_total
                daily[day]["orders"] += 1

        for po in pos:
            day = fields.Date.to_date(po.date_order)
            if day in daily:
                daily[day]["purchase"] += po.amount_total

        for p_o in prev_orders:
            mapped_day = fields.Date.to_date(p_o.date_order) + timedelta(days=offset)
            if mapped_day in daily:
                daily[mapped_day]["prev_sales"] += p_o.amount_total

        max_val = max(
            [max(v["sales"], v["prev_sales"], v["purchase"]) for v in daily.values()] or [1.0]
        ) or 1.0

        return [
            Command.create({
                "period_date": day,
                "label": day.strftime("%d %b"),
                "sales_amount": round(v["sales"], 2),
                "prev_sales_amount": round(v["prev_sales"], 2),
                "purchase_amount": round(v["purchase"], 2),
                "order_count": v["orders"],
                "sales_bar_pct": round(v["sales"] / max_val * 100.0, 1),
                "purchase_bar_pct": round(v["purchase"] / max_val * 100.0, 1),
            })
            for day, v in sorted(daily.items())
        ]

    def _compute_period_metrics(self, date_from, date_to, company, partner=None, sales_channel=None, payment_mode=None):
        span = max(1, (date_to - date_from).days + 1)
        prev_to = date_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=span - 1)

        orders = self.env["sale.order"].search(
            self._build_sale_domain(company, date_from, date_to, partner, sales_channel, payment_mode)
        )
        prev_orders = self.env["sale.order"].search(
            self._build_sale_domain(company, prev_from, prev_to, partner, sales_channel, payment_mode)
        )

        dt_from = fields.Datetime.to_datetime(date_from)
        dt_to = fields.Datetime.to_datetime(date_to) + timedelta(days=1)
        pos = self.env["purchase.order"].search([
            ("company_id", "=", company.id),
            ("state", "in", ("purchase", "done")),
            ("date_order", ">=", dt_from),
            ("date_order", "<", dt_to),
        ])
        p_dt_from = fields.Datetime.to_datetime(prev_from)
        p_dt_to = fields.Datetime.to_datetime(prev_to) + timedelta(days=1)
        prev_pos = self.env["purchase.order"].search([
            ("company_id", "=", company.id),
            ("state", "in", ("purchase", "done")),
            ("date_order", ">=", p_dt_from),
            ("date_order", "<", p_dt_to),
        ])

        metrics = {}
        metrics.update(self._compute_sales_metrics(orders, prev_orders))
        metrics.update(self._compute_purchase_metrics(pos, prev_pos))
        metrics.update(self._compute_stock_metrics(company))
        metrics.update(self._compute_finance_crm_ops_metrics(date_from, date_to, company, partner))
        metrics["trend_line_ids"] = self._compute_trend_lines(date_from, date_to, prev_from, orders, prev_orders, pos)
        return metrics

    def get_chart_payload_json(self):
        self.ensure_one()
        payload = {
            "currency": self.currency_id.symbol or "₹",
            "trend": {
                "labels": [t.label for t in self.trend_line_ids],
                "sales": [t.sales_amount for t in self.trend_line_ids],
                "prev_sales": [t.prev_sales_amount for t in self.trend_line_ids],
                "purchase": [t.purchase_amount for t in self.trend_line_ids],
            },
            "channels": {
                "labels": [c.channel_name for c in self.channel_line_ids],
                "revenue": [c.revenue for c in self.channel_line_ids],
                "orders": [c.order_count for c in self.channel_line_ids],
                "cod": [c.cod_count for c in self.channel_line_ids],
            },
            "customers": {
                "labels": [c.partner_id.display_name for c in self.customer_line_ids[:8]],
                "revenue": [c.revenue for c in self.customer_line_ids[:8]],
                "orders": [c.order_count for c in self.customer_line_ids[:8]],
            },
            "payment_mix": {
                "labels": ["Prepaid", "COD (Non-RTO)", "RTO"],
                "values": [
                    self.prepaid_order_count,
                    max(0, self.cod_order_count - self.rto_order_count),
                    self.rto_order_count,
                ],
            },
            "modules": {
                "labels": [
                    "Sales Orders",
                    "Gross Margin",
                    "Invoiced Rev",
                    "Purchase Spend",
                    "CRM Pipeline",
                    "Active MRR",
                    "Payroll",
                ],
                "current": [
                    self.total_sales,
                    self.total_margin,
                    self.invoiced_revenue,
                    self.purchase_spend,
                    self.crm_pipeline_value,
                    self.active_mrr,
                    self.payroll_total,
                ],
            },
        }
        return json.dumps(payload)

    def _reload_with_days(self, days):
        self.ensure_one()
        self.date_to = fields.Date.today()
        self.date_from = self.date_to - timedelta(days=days)
        return self.action_refresh()

    def action_preset_7d(self):
        return self._reload_with_days(7)

    def action_preset_30d(self):
        return self._reload_with_days(30)

    def action_preset_90d(self):
        return self._reload_with_days(90)

    def action_refresh(self):
        self.ensure_one()
        self.channel_line_ids.unlink()
        self.customer_line_ids.unlink()
        self.product_line_ids.unlink()
        self.vendor_line_ids.unlink()
        self.stock_line_ids.unlink()
        self.trend_line_ids.unlink()
        metrics = self._compute_period_metrics(
            self.date_from,
            self.date_to,
            self.company_id,
            partner=self.partner_id,
            sales_channel=self.sales_channel,
            payment_mode=self.payment_mode,
        )
        self.write(metrics)
        return {
            "type": "ir.actions.act_window",
            "name": _("Live Cross-ERP Analytics"),
            "res_model": "custom.analytics.board",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }


class CustomAnalyticsChannelLine(models.TransientModel):
    _name = "custom.analytics.channel.line"
    _description = "Analytics Channel Breakdown Row"
    _order = "revenue desc"

    board_id = fields.Many2one("custom.analytics.board", required=True, ondelete="cascade")
    channel_name = fields.Char(required=True)
    order_count = fields.Integer()
    currency_id = fields.Many2one(related="board_id.currency_id", readonly=True)
    revenue = fields.Monetary()
    share_pct = fields.Float(string="Share %")
    bar_pct = fields.Float(string="Relative Bar %")
    cod_count = fields.Integer(string="COD Orders")
    rto_count = fields.Integer(string="RTO Orders")


class CustomAnalyticsCustomerLine(models.TransientModel):
    _name = "custom.analytics.customer.line"
    _description = "Analytics Customer Comparison Row"
    _order = "revenue desc"

    board_id = fields.Many2one("custom.analytics.board", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    order_count = fields.Integer(string="Orders")
    currency_id = fields.Many2one(related="board_id.currency_id", readonly=True)
    revenue = fields.Monetary()
    share_pct = fields.Float(string="Share %")
    cod_count = fields.Integer(string="COD Orders")


class CustomAnalyticsProductLine(models.TransientModel):
    _name = "custom.analytics.product.line"
    _description = "Analytics Top Product Row"
    _order = "revenue desc"

    board_id = fields.Many2one("custom.analytics.board", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True)
    units_sold = fields.Float()
    currency_id = fields.Many2one(related="board_id.currency_id", readonly=True)
    revenue = fields.Monetary()


class CustomAnalyticsVendorLine(models.TransientModel):
    _name = "custom.analytics.vendor.line"
    _description = "Analytics Top Vendor Row"
    _order = "total_spend desc"

    board_id = fields.Many2one("custom.analytics.board", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Vendor", required=True)
    po_count = fields.Integer(string="PO Count")
    currency_id = fields.Many2one(related="board_id.currency_id", readonly=True)
    total_spend = fields.Monetary()


class CustomAnalyticsStockLine(models.TransientModel):
    _name = "custom.analytics.stock.line"
    _description = "Analytics Stock & Low-Stock Row"

    board_id = fields.Many2one("custom.analytics.board", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True)
    qty_on_hand = fields.Float(string="On Hand")
    qty_reserved = fields.Float(string="Reserved")
    qty_available = fields.Float(string="Available")
    currency_id = fields.Many2one(related="board_id.currency_id", readonly=True)
    stock_value = fields.Monetary(string="Cost Value")
    is_low_stock = fields.Boolean(string="Low Stock")


class CustomAnalyticsTrendLine(models.TransientModel):
    _name = "custom.analytics.trend.line"
    _description = "Analytics Daily Trend Point"
    _order = "period_date asc"

    board_id = fields.Many2one("custom.analytics.board", required=True, ondelete="cascade")
    period_date = fields.Date(required=True)
    label = fields.Char(required=True)
    order_count = fields.Integer()
    currency_id = fields.Many2one(related="board_id.currency_id", readonly=True)
    sales_amount = fields.Monetary()
    prev_sales_amount = fields.Monetary(string="Prev. Period Sales")
    purchase_amount = fields.Monetary()
    sales_bar_pct = fields.Float()
    purchase_bar_pct = fields.Float()
