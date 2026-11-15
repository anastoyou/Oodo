from datetime import timedelta

from odoo import _, api, fields, models


class CustomSupportTeam(models.Model):
    _name = "custom.support.team"
    _description = "Helpdesk Support Team (Round-Robin)"
    _order = "name"

    name = fields.Char(required=True)
    member_ids = fields.Many2many("res.users", string="Team Agents", domain="[('share', '=', False)]")
    auto_assign_round_robin = fields.Boolean(string="Round-Robin Auto-Assignment", default=True)
    last_assigned_user_id = fields.Many2one("res.users", readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    def _next_round_robin_user(self):
        self.ensure_one()
        members = self.member_ids.sorted("id")
        if not members:
            return False
        if self.last_assigned_user_id and self.last_assigned_user_id in members:
            idx = list(members.ids).index(self.last_assigned_user_id.id)
            next_user = members[(idx + 1) % len(members)]
        else:
            next_user = members[0]
        self.last_assigned_user_id = next_user.id
        return next_user


class CustomSupportSla(models.Model):
    _name = "custom.support.sla"
    _description = "Helpdesk SLA Policy"
    _order = "priority desc, id asc"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    team_id = fields.Many2one("custom.support.team", string="Support Team")
    category = fields.Selection(
        [
            ("all", "All Categories"),
            ("size_exchange", "Size / Fit Exchange"),
            ("delivery_tracking", "Delivery / Tracking Status"),
            ("cod_verification", "COD Order Verification"),
            ("defect_damage", "Damaged / Incorrect Item"),
            ("return_refund", "Return & Refund Request"),
            ("payment_gst", "Payment / GST Invoice"),
            ("other", "General Inquiry"),
        ],
        default="all",
        required=True,
    )
    priority = fields.Selection(
        [("0", "Normal"), ("1", "Medium"), ("2", "High"), ("3", "Urgent")],
        string="Minimum Priority",
        default="1",
        required=True,
    )
    resolution_hours = fields.Float(string="Target Resolution (Hours)", default=24.0, required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomSupportCannedResponse(models.Model):
    _name = "custom.support.canned.response"
    _description = "Helpdesk Canned Response Macro"
    _order = "shortcut"

    name = fields.Char(required=True)
    shortcut = fields.Char(required=True, help="Short trigger keyword, e.g. /size-exchange")
    body = fields.Text(required=True)


class CustomSupportTicketEnterprise(models.Model):
    _inherit = "custom.support.ticket"

    team_id = fields.Many2one("custom.support.team", string="Support Team", tracking=True)
    sla_id = fields.Many2one("custom.support.sla", string="Applied SLA", tracking=True)
    sla_deadline = fields.Datetime(string="SLA Deadline", tracking=True)
    sla_status = fields.Selection(
        [
            ("none", "No SLA"),
            ("on_track", "On Track"),
            ("due_soon", "Due Soon (<4h)"),
            ("breached", "SLA Breached"),
            ("met", "SLA Met"),
        ],
        compute="_compute_sla_status",
        store=True,
    )
    canned_response_id = fields.Many2one(
        "custom.support.canned.response",
        string="Insert Canned Response",
        store=False,
    )
    rating_score = fields.Selection(
        [("1", "1 - Poor"), ("2", "2 - Fair"), ("3", "3 - Good"), ("4", "4 - Great"), ("5", "5 - Excellent")],
        string="CSAT Rating",
        tracking=True,
    )
    rating_comment = fields.Text(string="Customer Feedback")
    rating_date = fields.Datetime(string="Rated At", readonly=True)

    @api.depends("sla_deadline", "stage", "closed_date")
    def _compute_sla_status(self):
        now = fields.Datetime.now()
        for ticket in self:
            if not ticket.sla_deadline:
                ticket.sla_status = "none"
                continue
            if ticket.stage in ("resolved", "closed"):
                ref_dt = ticket.closed_date or now
                ticket.sla_status = "met" if ref_dt <= ticket.sla_deadline else "breached"
            elif now > ticket.sla_deadline:
                ticket.sla_status = "breached"
            elif now + timedelta(hours=4) >= ticket.sla_deadline:
                ticket.sla_status = "due_soon"
            else:
                ticket.sla_status = "on_track"

    def _find_matching_sla(self, category, priority, team_id):
        slas = self.env["custom.support.sla"].search([("active", "=", True)], order="priority desc, resolution_hours asc")
        for sla in slas:
            if sla.team_id and team_id and sla.team_id.id != team_id:
                continue
            if sla.category not in ("all", category):
                continue
            if int(priority or "0") >= int(sla.priority or "0"):
                return sla
        return False

    @api.model_create_multi
    def create(self, vals_list):
        default_team = self.env["custom.support.team"].search([], limit=1)
        for vals in vals_list:
            if not vals.get("team_id") and default_team:
                vals["team_id"] = default_team.id
            if not vals.get("user_id") and vals.get("team_id"):
                team = self.env["custom.support.team"].browse(vals["team_id"])
                if team.auto_assign_round_robin:
                    agent = team._next_round_robin_user()
                    if agent:
                        vals["user_id"] = agent.id
            if not vals.get("sla_id"):
                sla = self._find_matching_sla(
                    vals.get("category", "other"),
                    vals.get("priority", "1"),
                    vals.get("team_id"),
                )
                if sla:
                    vals["sla_id"] = sla.id
                    vals["sla_deadline"] = fields.Datetime.now() + timedelta(hours=sla.resolution_hours)
        return super().create(vals_list)

    def action_post_canned_response(self):
        for ticket in self:
            if ticket.canned_response_id:
                ticket.message_post(body=ticket.canned_response_id.body)
                ticket.canned_response_id = False

    @api.model
    def _cron_check_sla_breaches(self):
        tickets = self.search([
            ("stage", "in", ("new", "in_progress", "waiting_customer")),
            ("sla_deadline", "!=", False),
        ])
        tickets._compute_sla_status()

