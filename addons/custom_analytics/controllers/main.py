from datetime import timedelta

from odoo import fields, http
from odoo.http import request

from ..models.roadmap_tracker import PHASE_META


class CustomAnalyticsController(http.Controller):
    """Interactive /analytics Executive Dashboard & Scaling Phase 1-5 Tracker."""

    @http.route(["/analytics"], type="http", auth="user", website=True)
    def analytics_web_dashboard(
        self,
        days="30",
        date_from="",
        date_to="",
        partner_id="",
        channel="",
        payment_mode="",
        module="all",
        **kwargs,
    ):
        try:
            n_days = max(1, min(365, int(days)))
        except (TypeError, ValueError):
            n_days = 30

        d_to = fields.Date.to_date(date_to) if date_to else fields.Date.today()
        d_from = fields.Date.to_date(date_from) if date_from else (d_to - timedelta(days=n_days))
        if d_from > d_to:
            d_from, d_to = d_to, d_from

        selected_partner_id = int(partner_id) if str(partner_id).isdigit() else False
        allowed_modules = {"all", "sales_crm", "purchase_stock", "finance", "ops_hr"}
        active_module = module if module in allowed_modules else "all"

        valid_channels = {k for k, _lbl in request.env["sale.order"]._fields["x_sales_channel"].selection}
        selected_channel = channel if channel in valid_channels else False
        selected_payment = payment_mode if payment_mode in ("prepaid", "cod") else False

        board = request.env["custom.analytics.board"].create({
            "date_from": d_from,
            "date_to": d_to,
            "partner_id": selected_partner_id,
            "sales_channel": selected_channel,
            "payment_mode": selected_payment,
            "active_module": active_module,
        })
        board.action_refresh()
        roadmap = request.env["custom.roadmap.snapshot"].get_or_evaluate_latest(persist=False)

        customers = request.env["res.partner"].search(
            [("customer_rank", ">", 0)],
            order="name asc",
            limit=200,
        )
        if not customers:
            customers = request.env["res.partner"].search([("is_company", "=", True)], limit=100)

        channels = list(request.env["sale.order"]._fields["x_sales_channel"].selection)
        return request.render(
            "custom_analytics.analytics_dashboard_page",
            {
                "board": board,
                "roadmap": roadmap,
                "days": n_days,
                "customers": customers,
                "channels": channels,
                "selected_partner_id": selected_partner_id,
                "selected_channel": selected_channel or "",
                "selected_payment": selected_payment or "",
                "active_module": active_module,
                "chart_json": board.get_chart_payload_json(),
            },
        )

    @http.route(["/analytics/roadmap"], type="http", auth="user", website=True)
    def analytics_roadmap_tracker(self, **kwargs):
        roadmap = request.env["custom.roadmap.snapshot"].get_or_evaluate_latest(persist=False)
        phases = [
            {
                "key": k,
                "title": PHASE_META[k]["title"],
                "rev_band": PHASE_META[k]["rev_band"],
                "is_current": roadmap.current_phase == k,
                "is_done": int(roadmap.current_phase) > int(k),
            }
            for k in ("1", "2", "3", "4", "5")
        ]
        return request.render(
            "custom_analytics.roadmap_tracker_page",
            {
                "roadmap": roadmap,
                "phases": phases,
            },
        )

    @http.route(["/analytics/roadmap/promote"], type="http", auth="user", methods=["POST"], website=True)
    def analytics_roadmap_promote(self, **kwargs):
        roadmap = request.env["custom.roadmap.snapshot"].get_or_evaluate_latest()
        if roadmap.ready_for_next_phase and roadmap.current_phase != "5":
            roadmap.action_promote_next_phase()
        return request.redirect("/analytics/roadmap")
