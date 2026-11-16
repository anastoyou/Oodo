from datetime import timedelta

from odoo import Command, _, api, fields, models


PHASE_META = {
    "1": {
        "title": "Phase 1: Surat Seed (Zero-Stock Dropship)",
        "rev_band": "₹0 – ₹3 L / month",
        "next": "2",
        "next_title": "Phase 2: Own Stock & Brand (Micro-Godown + Marketplaces)",
        "unlocks": "300–800 sq ft Godown, Bestseller Stocking, Myntra/Ajio/Amazon/Flipkart/Meesho, Hang-Tag Labels",
        "min_rev": 300000.0,
        "min_margin_pct": 20.0,
        "min_cash": 250000.0,
        "min_customers": 1000,
        "min_repeat_pct": 15.0,
        "max_rto_pct": 25.0,
        "min_top_sku_pct": 50.0,
    },
    "2": {
        "title": "Phase 2: Own Stock & Brand (Godown + Marketplaces)",
        "rev_band": "₹3 L – ₹15 L / month",
        "next": "3",
        "next_title": "Phase 3: Own Label + Men's Category + First Store",
        "unlocks": "Own-Label Job-Work Production, Men's Category, First High-Street Surat Store (POS)",
        "min_rev": 1500000.0,
        "min_margin_pct": 25.0,
        "min_cash": 1250000.0,
        "min_customers": 10000,
        "min_repeat_pct": 25.0,
        "min_turns": 4.0,
        "max_rto_pct": 20.0,
    },
    "3": {
        "title": "Phase 3: Own Label + First Store + Men's",
        "rev_band": "₹15 L – ₹50 L / month",
        "next": "4",
        "next_title": "Phase 4: Central Warehouse + 5 Stores + Kids",
        "unlocks": "5,000+ sq ft Central Warehouse, Up to 5 Retail Stores (POS), Kids Category, Helpdesk+ & Approvals",
        "min_rev": 5000000.0,
        "min_margin_pct": 25.0,
        "min_cash": 5000000.0,
        "min_customers": 25000,
        "min_repeat_pct": 28.0,
        "min_cities": 3,
        "min_warehouses": 2,
    },
    "4": {
        "title": "Phase 4: Central Warehouse + 5 Stores + Kids",
        "rev_band": "₹50 L – ₹1.5 Cr / month",
        "next": "5",
        "next_title": "Phase 5: Lifestyle Brand + New Verticals + Franchise",
        "unlocks": "Footwear, Fabrics & Gadgets Verticals, Franchise Store Network (FR01+), Inter-Company Auto-Sync",
        "min_rev": 15000000.0,
        "min_margin_pct": 28.0,
        "min_cash": 10000000.0,
        "min_customers": 100000,
        "min_repeat_pct": 30.0,
        "min_turns": 5.0,
        "min_warehouses": 5,
    },
    "5": {
        "title": "Phase 5: Multi-Category Lifestyle Brand + Franchise",
        "rev_band": "₹1.5 Cr+ / month",
        "next": False,
        "next_title": "All Roadmap Phases Unlocked",
        "unlocks": "Pan-India Franchise Network, Multi-Website Brands & International D2C Expansion",
    },
}


class CustomRoadmapSnapshot(models.Model):
    _name = "custom.roadmap.snapshot"
    _description = "Scaling Roadmap Phase Gate Progress & Alerts"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "evaluated_date desc, id desc"

    name = fields.Char(required=True, default=lambda self: f"Phase Check {fields.Date.today()}")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    evaluated_date = fields.Date(required=True, default=fields.Date.context_today)

    current_phase = fields.Selection(
        [
            ("1", "Phase 1: Surat Seed (Online Dropship)"),
            ("2", "Phase 2: Own Stock & Micro-Godown"),
            ("3", "Phase 3: Own Label + Men's + Store #1"),
            ("4", "Phase 4: Central WH + 5 Stores + Kids"),
            ("5", "Phase 5: Lifestyle Brand + Franchise"),
        ],
        required=True,
        default="1",
        tracking=True,
    )
    next_phase_label = fields.Char(readonly=True)
    next_phase_unlocks = fields.Char(readonly=True)
    gate_progress_pct = fields.Float(string="Next Gate Readiness %", readonly=True)
    must_cleared_count = fields.Integer(readonly=True)
    must_total_count = fields.Integer(readonly=True)
    signal_cleared_count = fields.Integer(readonly=True)
    signal_total_count = fields.Integer(readonly=True)
    consecutive_months_cleared = fields.Integer(string="Consecutive Months Hit (Target 3)", readonly=True)
    ready_for_next_phase = fields.Boolean(string="Next Phase Gate Cleared", readonly=True, tracking=True)
    alert_level = fields.Selection(
        [("tracking", "Tracking Progress"), ("warning", "Near Gate (>=75%)"), ("ready", "Ready for Next Phase!")],
        default="tracking",
        readonly=True,
    )
    alert_banner = fields.Text(readonly=True)

    # Measured Live ERP Metrics
    net_revenue_30d = fields.Monetary(string="Last 30d Net Revenue", readonly=True)
    net_revenue_m2 = fields.Monetary(string="Prev 31–60d Revenue", readonly=True)
    net_revenue_m3 = fields.Monetary(string="Prev 61–90d Revenue", readonly=True)
    margin_pct = fields.Float(string="Contribution / Gross Margin %", readonly=True)
    cash_reserve = fields.Monetary(string="Bank & Cash Liquidity", readonly=True)
    total_customers = fields.Integer(string="Total Unique Customers", readonly=True)
    repeat_customer_pct = fields.Float(string="Repeat Customer %", readonly=True)
    rto_rate_pct = fields.Float(string="RTO Rate %", readonly=True)
    top_sku_share_pct = fields.Float(string="Top 20 SKU Sales Share %", readonly=True)
    inventory_value = fields.Monetary(string="Stock Value", readonly=True)
    inventory_turns = fields.Float(string="Annualized Inventory Turns", readonly=True)
    active_warehouses = fields.Integer(string="Active Warehouses / Stores", readonly=True)
    active_websites = fields.Integer(string="Active Websites / Units", readonly=True)
    ready_for_new_website = fields.Boolean(string="Ready for New Website / Unit", readonly=True)
    website_unit_advice = fields.Text(string="New Website / Unit Guidance", readonly=True)
    distinct_cities = fields.Integer(string="Customer City Clusters", readonly=True)

    criteria_line_ids = fields.One2many("custom.roadmap.criteria", "snapshot_id", string="Gate Criteria Checklist")

    def _window_revenue(self, company, d_from, d_to):
        orders = self.env["sale.order"].search([
            ("company_id", "=", company.id),
            ("state", "=", "sale"),
            ("date_order", ">=", fields.Datetime.to_datetime(d_from)),
            ("date_order", "<", fields.Datetime.to_datetime(d_to) + timedelta(days=1)),
        ])
        valid = orders.filtered(lambda o: not o.x_is_rto)
        return round(sum(valid.mapped("amount_total")), 2), orders

    def _collect_erp_metrics(self, company):
        today = fields.Date.today()
        rev_m1, orders_m1 = self._window_revenue(company, today - timedelta(days=29), today)
        rev_m2, _ = self._window_revenue(company, today - timedelta(days=59), today - timedelta(days=30))
        rev_m3, _ = self._window_revenue(company, today - timedelta(days=89), today - timedelta(days=60))

        total_sales_m1 = sum(orders_m1.mapped("amount_total"))
        total_margin_m1 = sum(orders_m1.mapped("margin")) if "margin" in orders_m1._fields else 0.0
        margin_pct = round((total_margin_m1 / total_sales_m1 * 100.0), 1) if total_sales_m1 else 0.0
        rto_count = len(orders_m1.filtered(lambda o: o.x_is_rto))
        rto_rate_pct = round((rto_count / len(orders_m1) * 100.0), 1) if orders_m1 else 0.0

        # Bank & Cash Reserve from posted journal items on Liquidity accounts
        cash_accounts = self.env["account.account"].search([
            ("account_type", "=", "asset_cash"),
            ("company_ids", "in", [company.id]),
        ])
        cash_lines = self.env["account.move.line"].search([
            ("company_id", "=", company.id),
            ("parent_state", "=", "posted"),
            ("account_id", "in", cash_accounts.ids),
        ]) if cash_accounts else self.env["account.move.line"]
        cash_reserve = round(sum(cash_lines.mapped("balance")), 2)

        # Customer count, repeat %, city clusters from all confirmed sales
        all_sales = self.env["sale.order"].search([
            ("company_id", "=", company.id),
            ("state", "=", "sale"),
        ])
        cust_counts = {}
        cities = set()
        for o in all_sales:
            if o.partner_id:
                cust_counts[o.partner_id.id] = cust_counts.get(o.partner_id.id, 0) + 1
                if o.partner_id.city:
                    cities.add(o.partner_id.city.strip().lower())
        total_customers = len(cust_counts)
        repeat_count = sum(1 for cnt in cust_counts.values() if cnt >= 2)
        repeat_pct = round((repeat_count / total_customers * 100.0), 1) if total_customers else 0.0

        # Top 20 SKU concentration in last 30d
        sku_rev = {}
        for line in orders_m1.mapped("order_line"):
            if line.product_id:
                sku_rev[line.product_id.id] = sku_rev.get(line.product_id.id, 0.0) + line.price_subtotal
        sorted_skus = sorted(sku_rev.values(), reverse=True)
        top20_rev = sum(sorted_skus[:20])
        sum_sku_rev = sum(sorted_skus)
        top_sku_share = round((top20_rev / sum_sku_rev * 100.0), 1) if sum_sku_rev else 0.0

        # Inventory Value & Turns
        quants = self.env["stock.quant"].search([
            ("company_id", "=", company.id),
            ("location_id.usage", "=", "internal"),
        ])
        inv_val = round(sum(q.quantity * q.product_id.standard_price for q in quants), 2)
        cogs_30d = max(0.0, total_sales_m1 - total_margin_m1)
        turns = round(((cogs_30d * 12.0) / inv_val), 2) if inv_val > 0 else 0.0

        wh_count = self.env["stock.warehouse"].search_count([("company_id", "=", company.id)])
        site_count = self.env["website"].search_count([])

        return {
            "net_revenue_30d": rev_m1,
            "net_revenue_m2": rev_m2,
            "net_revenue_m3": rev_m3,
            "margin_pct": margin_pct,
            "cash_reserve": cash_reserve,
            "total_customers": total_customers,
            "repeat_customer_pct": repeat_pct,
            "rto_rate_pct": rto_rate_pct,
            "top_sku_share_pct": top_sku_share,
            "inventory_value": inv_val,
            "inventory_turns": turns,
            "active_warehouses": wh_count,
            "active_websites": site_count,
            "distinct_cities": len(cities),
        }

    def _build_criteria_rows(self, phase, m):
        meta = PHASE_META.get(phase, PHASE_META["1"])
        if not meta.get("next"):
            return [], 100.0, 0, 0, 0, 0, 3, True

        min_rev = meta["min_rev"]
        streak = sum(1 for val in (m["net_revenue_30d"], m["net_revenue_m2"], m["net_revenue_m3"]) if val >= min_rev)

        def pct_up(actual, target):
            return round(min(100.0, max(0.0, (actual / target * 100.0) if target else 100.0)), 1)

        def pct_cap(actual, max_limit, has_orders):
            if not has_orders:
                return 0.0
            return 100.0 if actual <= max_limit else round(max(0.0, (max_limit / actual) * 100.0), 1)

        specs = [
            ("must", "Monthly Net Revenue", f"₹{min_rev:,.0f}+", f"₹{m['net_revenue_30d']:,.0f}", pct_up(m["net_revenue_30d"], min_rev), m["net_revenue_30d"] >= min_rev),
            ("streak", "3 Consecutive Months Target", "3 / 3 months", f"{streak} / 3 months", round(streak / 3.0 * 100.0, 1), streak >= 3),
            ("must", "Contribution / Gross Margin %", f">= {meta['min_margin_pct']:.0f}%", f"{m['margin_pct']:.1f}%", pct_up(m["margin_pct"], meta["min_margin_pct"]), m["margin_pct"] >= meta["min_margin_pct"]),
            ("must", "Cash Reserve (Bank + Cash)", f"₹{meta['min_cash']:,.0f}+", f"₹{m['cash_reserve']:,.0f}", pct_up(m["cash_reserve"], meta["min_cash"]), m["cash_reserve"] >= meta["min_cash"]),
            ("must", "Total Unique Customers", f"{meta['min_customers']:,}+", f"{m['total_customers']:,}", pct_up(m["total_customers"], meta["min_customers"]), m["total_customers"] >= meta["min_customers"]),
            ("signal", "Repeat Customer Rate %", f">= {meta['min_repeat_pct']:.0f}%", f"{m['repeat_customer_pct']:.1f}%", pct_up(m["repeat_customer_pct"], meta["min_repeat_pct"]), m["repeat_customer_pct"] >= meta["min_repeat_pct"]),
        ]

        if "max_rto_pct" in meta:
            has_ord = m["net_revenue_30d"] > 0 or m["total_customers"] > 0
            specs.append(("signal", "RTO Control (Lower is Better)", f"<= {meta['max_rto_pct']:.0f}%", f"{m['rto_rate_pct']:.1f}%", pct_cap(m["rto_rate_pct"], meta["max_rto_pct"], has_ord), has_ord and m["rto_rate_pct"] <= meta["max_rto_pct"]))
        if "min_top_sku_pct" in meta:
            specs.append(("signal", "Top-20 Bestseller SKU Share", f">= {meta['min_top_sku_pct']:.0f}%", f"{m['top_sku_share_pct']:.1f}%", pct_up(m["top_sku_share_pct"], meta["min_top_sku_pct"]), m["top_sku_share_pct"] >= meta["min_top_sku_pct"]))
        if "min_turns" in meta:
            specs.append(("signal", "Annualized Inventory Turns", f">= {meta['min_turns']:.1f}x", f"{m['inventory_turns']:.1f}x", pct_up(m["inventory_turns"], meta["min_turns"]), m["inventory_turns"] >= meta["min_turns"]))
        if "min_cities" in meta:
            specs.append(("signal", "Customer City Clusters", f"{meta['min_cities']}+ cities", f"{m['distinct_cities']} cities", pct_up(m["distinct_cities"], meta["min_cities"]), m["distinct_cities"] >= meta["min_cities"]))
        if "min_warehouses" in meta:
            specs.append(("signal", "Active Warehouses / Stores", f"{meta['min_warehouses']}+", f"{m['active_warehouses']}", pct_up(m["active_warehouses"], meta["min_warehouses"]), m["active_warehouses"] >= meta["min_warehouses"]))

        must_rows = [s for s in specs if s[0] in ("must", "streak")]
        sig_rows = [s for s in specs if s[0] == "signal"]
        must_ok = sum(1 for s in must_rows if s[5])
        sig_ok = sum(1 for s in sig_rows if s[5])
        # Overall gate progress weights Must-Have + Streak (75%) and Signals (25%)
        must_avg = sum(s[4] for s in must_rows) / len(must_rows) if must_rows else 100.0
        sig_avg = sum(s[4] for s in sig_rows) / len(sig_rows) if sig_rows else 100.0
        overall = round(must_avg * 0.75 + sig_avg * 0.25, 1)
        ready = (must_ok == len(must_rows)) and (sig_ok >= min(2, len(sig_rows)))

        cmds = [
            Command.create({
                "criteria_type": s[0],
                "name": s[1],
                "target_display": s[2],
                "actual_display": s[3],
                "progress_pct": s[4],
                "is_met": s[5],
            })
            for s in specs
        ]
        return cmds, overall, must_ok, len(must_rows), sig_ok, len(sig_rows), streak, ready

    def _compute_snapshot_vals(self, company, current_phase):
        """Evaluate metrics and gate criteria for *company* without writing to DB."""
        metrics = self._collect_erp_metrics(company)
        cmds, overall, must_ok, must_tot, sig_ok, sig_tot, streak, ready = self._build_criteria_rows(
            current_phase, metrics
        )
        meta = PHASE_META.get(current_phase, PHASE_META["1"])

        if not meta.get("next"):
            level = "ready"
            banner = _("Phase 5 Reached: All roadmap scaling phases are active.")
        elif ready:
            level = "ready"
            banner = _(
                "READY TO MOVE TO PHASE %(next)s: All %(must)s/%(mtot)s must-have criteria, "
                "%(sig)s/%(stot)s signals, and 3-month sustained revenue cleared!"
            ) % {
                "next": meta["next"],
                "must": must_ok,
                "mtot": must_tot,
                "sig": sig_ok,
                "stot": sig_tot,
            }
        elif overall >= 75.0:
            level = "warning"
            banner = _(
                "APPROACHING GATE %(cur)s (%(pct).1f%% Ready): %(must)s/%(mtot)s must-have met, "
                "%(sig)s/%(stot)s signals met, %(st)s/3 consecutive months cleared."
            ) % {
                "cur": current_phase,
                "pct": overall,
                "must": must_ok,
                "mtot": must_tot,
                "sig": sig_ok,
                "stot": sig_tot,
                "st": streak,
            }
        else:
            level = "tracking"
            banner = _(
                "Phase %(cur)s in Progress (%(pct).1f%% toward %(next)s): %(must)s/%(mtot)s must-have met, "
                "%(sig)s/%(stot)s signals, %(st)s/3 consecutive months."
            ) % {
                "cur": current_phase,
                "pct": overall,
                "next": meta.get("next_title"),
                "must": must_ok,
                "mtot": must_tot,
                "sig": sig_ok,
                "stot": sig_tot,
                "st": streak,
            }

        ready_new_site = current_phase == "5" or (current_phase == "4" and (ready or overall >= 75.0))
        if ready_new_site:
            site_advice = _(
                "READY FOR NEW WEBSITE / BUSINESS UNIT (Active websites: %(cnt)s): You are in/entering Phase 5 expansion. "
                "You can launch a dedicated Website unit (e.g., separate Gadgets brand or B2B/Franchise portal) via "
                "Website -> Configuration -> Settings -> + New Website, set a separate Domain, and package views/styles "
                "following docs/MULTI_WEBSITE_AND_UNIT_GUIDE.md."
            ) % {"cnt": metrics["active_websites"]}
        else:
            site_advice = _(
                "KEEP 1 PRIMARY WEBSITE & USE URL PATHS (Active websites: %(cnt)s): During Phase %(cur)s, avoid splitting SEO "
                "across multiple domains. Add new collections/categories as paths (/ladies, /men, /kids) under Website -> Pages. "
                "New Website creation automatically unlocks at Phase 4 Gate -> Phase 5 (see docs/MULTI_WEBSITE_AND_UNIT_GUIDE.md)."
            ) % {"cnt": metrics["active_websites"], "cur": current_phase}

        vals = dict(metrics)
        vals.update({
            "evaluated_date": fields.Date.today(),
            "next_phase_label": meta.get("next_title", "Completed"),
            "next_phase_unlocks": meta.get("unlocks", ""),
            "gate_progress_pct": overall,
            "must_cleared_count": must_ok,
            "must_total_count": must_tot,
            "signal_cleared_count": sig_ok,
            "signal_total_count": sig_tot,
            "consecutive_months_cleared": streak,
            "ready_for_next_phase": ready,
            "ready_for_new_website": ready_new_site,
            "website_unit_advice": site_advice,
            "alert_level": level,
            "alert_banner": banner,
            "criteria_line_ids": cmds,
        })
        return vals

    def action_evaluate_now(self):
        for rec in self:
            was_ready = rec.ready_for_next_phase
            vals = rec._compute_snapshot_vals(rec.company_id, rec.current_phase)
            vals["criteria_line_ids"] = [Command.clear()] + vals["criteria_line_ids"]
            rec.write(vals)
            if rec.ready_for_next_phase and not was_ready:
                rec.message_post(body=rec.alert_banner)
        return True

    def action_promote_next_phase(self):
        self.ensure_one()
        meta = PHASE_META.get(self.current_phase, PHASE_META["1"])
        nxt = meta.get("next")
        if nxt:
            old_phase = self.current_phase
            self.current_phase = nxt
            self.action_evaluate_now()
            self.message_post(body=_("Promoted business roadmap from Phase %s to Phase %s.") % (old_phase, nxt))
        return True

    @api.model
    def get_or_evaluate_latest(self, company=None, persist=True):
        """Return live roadmap snapshot; pass persist=False on HTTP GET to avoid DB write contention."""
        company = company or self.env.company
        snap = self.search([("company_id", "=", company.id)], limit=1)
        if not persist:
            current_phase = snap.current_phase if snap else "1"
            name = snap.name if snap else "Scaling Roadmap Tracker"
            vals = self._compute_snapshot_vals(company, current_phase)
            return self.new({
                "company_id": company.id,
                "name": name,
                "current_phase": current_phase,
                **vals,
            })
        if not snap:
            snap = self.create({"company_id": company.id, "name": "Scaling Roadmap Tracker"})
        snap.action_evaluate_now()
        return snap

    @api.model
    def cron_check_roadmap_phase_gate(self):
        for company in self.env["res.company"].search([]):
            snap = self.get_or_evaluate_latest(company=company)
            if snap.ready_for_next_phase and snap.alert_level == "ready":
                admin = self.env.ref("base.user_admin", raise_if_not_found=False)
                if admin:
                    snap.activity_schedule(
                        "mail.mail_activity_data_todo",
                        user_id=admin.id,
                        summary=_("Scaling Gate Cleared: %s") % (snap.next_phase_label,),
                        note=snap.alert_banner or "",
                    )


class CustomRoadmapCriteria(models.Model):
    _name = "custom.roadmap.criteria"
    _description = "Roadmap Phase Gate Criterion Row"
    _order = "criteria_type asc, id asc"

    snapshot_id = fields.Many2one("custom.roadmap.snapshot", required=True, ondelete="cascade")
    criteria_type = fields.Selection(
        [("must", "Must-Have"), ("streak", "3-Month Streak"), ("signal", "Signal")],
        required=True,
    )
    name = fields.Char(string="Criterion", required=True)
    target_display = fields.Char(string="Target")
    actual_display = fields.Char(string="Actual (Live)")
    progress_pct = fields.Float(string="Progress %")
    is_met = fields.Boolean(string="Met")

