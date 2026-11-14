from odoo import _, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


ALLOWED_TICKET_CATEGORIES = {
    "size_exchange",
    "delivery_tracking",
    "cod_verification",
    "defect_damage",
    "return_refund",
    "payment_gst",
    "other",
}


class CustomStoreCustomerPortal(CustomerPortal):
    """Customer Portal extensions for Support & Size Exchange Tickets."""

    def _prepare_tickets_domain(self, partner):
        return [("partner_id", "child_of", [partner.commercial_partner_id.id])]

    def _prepare_portal_counter_values(self, counter):
        if counter == "ticket_count":
            partner = self.env.user.partner_id
            return "custom.support.ticket", self._prepare_tickets_domain(partner), "read"
        return super()._prepare_portal_counter_values(counter)

    @http.route(["/my/tickets", "/my/tickets/page/<int:page>"], type="http", auth="user", website=True)
    def portal_my_tickets(self, page=1, sortby=None, filterby=None, **kwargs):
        values = self._prepare_portal_layout_values()
        Ticket = request.env["custom.support.ticket"]
        partner = request.env.user.partner_id
        domain = list(self._prepare_tickets_domain(partner))

        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "create_date desc, id desc"},
            "priority": {"label": _("Priority"), "order": "priority desc, id desc"},
            "stage": {"label": _("Status"), "order": "stage asc, id desc"},
        }
        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
            "open": {"label": _("Open"), "domain": [("stage", "in", ("new", "in_progress", "waiting_customer"))]},
            "resolved": {"label": _("Resolved / Closed"), "domain": [("stage", "in", ("resolved", "closed"))]},
        }

        if not sortby or sortby not in searchbar_sortings:
            sortby = "date"
        if not filterby or filterby not in searchbar_filters:
            filterby = "all"

        domain += searchbar_filters[filterby]["domain"]
        order = searchbar_sortings[sortby]["order"]

        ticket_count = Ticket.search_count(domain)
        pager = portal_pager(
            url="/my/tickets",
            url_args={"sortby": sortby, "filterby": filterby},
            total=ticket_count,
            page=page,
            step=self._items_per_page,
        )
        tickets = Ticket.search(domain, order=order, limit=self._items_per_page, offset=pager["offset"])
        request.session["my_tickets_history"] = tickets.ids[:100]

        values.update({
            "tickets": tickets,
            "page_name": "support_ticket",
            "pager": pager,
            "default_url": "/my/tickets",
            "searchbar_sortings": searchbar_sortings,
            "sortby": sortby,
            "searchbar_filters": searchbar_filters,
            "filterby": filterby,
        })
        return request.render("custom_store.portal_my_tickets", values)

    @http.route(["/my/tickets/<int:ticket_id>"], type="http", auth="public", website=True)
    def portal_ticket_detail(self, ticket_id, access_token=None, **kwargs):
        try:
            ticket_sudo = self._document_check_access("custom.support.ticket", ticket_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._get_page_view_values(
            ticket_sudo,
            access_token,
            {"ticket": ticket_sudo, "page_name": "support_ticket"},
            "my_tickets_history",
            False,
            **kwargs,
        )
        return request.render("custom_store.portal_ticket_detail", values)


class CustomStoreSupportController(http.Controller):
    """Public and authenticated support submission routes (/support)."""

    def _get_support_context(self, **extra):
        user = request.env.user
        is_logged_in = not user._is_public()
        partner = user.partner_id if is_logged_in else request.env["res.partner"]
        orders = request.env["sale.order"]
        if is_logged_in:
            orders = request.env["sale.order"].search(
                [("partner_id", "child_of", [partner.commercial_partner_id.id]), ("state", "!=", "cancel")],
                order="date_order desc, id desc",
                limit=20,
            )
        ctx = {
            "is_logged_in": is_logged_in,
            "partner": partner,
            "user_orders": orders,
            "contact_name": extra.get("contact_name") or (partner.name if is_logged_in else ""),
            "contact_email": extra.get("contact_email") or (partner.email if is_logged_in else ""),
            "contact_phone": extra.get("contact_phone") or (partner.phone if is_logged_in else ""),
            "selected_order_id": extra.get("selected_order_id", ""),
            "selected_category": extra.get("selected_category", "size_exchange"),
            "subject": extra.get("subject", ""),
            "description": extra.get("description", ""),
            "error_message": extra.get("error_message", ""),
            "created_ticket": extra.get("created_ticket"),
        }
        return ctx

    @http.route("/support", type="http", auth="public", website=True, sitemap=True)
    def support_center(self, order_ref=None, **kwargs):
        ctx = self._get_support_context(
            subject=f"Order Help: {order_ref}" if order_ref else "",
            selected_order_id=kwargs.get("order_id", ""),
        )
        return request.render("custom_store.support_center_page", ctx)

    @http.route("/support/submit", type="http", auth="public", methods=["POST"], website=True, csrf=True)
    def support_submit(self, **post):
        contact_name = (post.get("contact_name") or "").strip()
        contact_email = (post.get("contact_email") or "").strip()
        contact_phone = (post.get("contact_phone") or "").strip()
        subject = (post.get("subject") or "").strip()
        description = (post.get("description") or "").strip()
        category = (post.get("category") or "other").strip()
        if category not in ALLOWED_TICKET_CATEGORIES:
            category = "other"

        if not contact_name or not contact_email or not subject:
            ctx = self._get_support_context(
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                selected_order_id=post.get("sale_order_id", ""),
                selected_category=category,
                subject=subject,
                description=description,
                error_message=_("Please fill in your name, email address, and subject."),
            )
            return request.render("custom_store.support_center_page", ctx)

        user = request.env.user
        is_logged_in = not user._is_public()
        vals = {
            "subject": subject,
            "description": description or subject,
            "contact_name": contact_name,
            "contact_email": contact_email,
            "contact_phone": contact_phone,
            "category": category,
        }

        if is_logged_in:
            partner = user.partner_id
            vals["partner_id"] = partner.id
            raw_order_id = (post.get("sale_order_id") or "").strip()
            if raw_order_id.isdigit():
                order = request.env["sale.order"].search([
                    ("id", "=", int(raw_order_id)),
                    ("partner_id", "child_of", [partner.commercial_partner_id.id]),
                ], limit=1)
                if order:
                    vals["sale_order_id"] = order.id

        ticket = request.env["custom.support.ticket"].sudo().create(vals)
        ctx = self._get_support_context(created_ticket=ticket)
        return request.render("custom_store.support_center_page", ctx)

