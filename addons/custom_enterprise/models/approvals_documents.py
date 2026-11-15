from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class CustomApprovalCategory(models.Model):
    _name = "custom.approval.category"
    _description = "Approval Request Type"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    description = fields.Char()
    approval_minimum = fields.Integer(string="Minimum Approvals", default=1, required=True)
    amount_threshold = fields.Float(string="Mandatory Above Amount", default=0.0)
    approver_ids = fields.Many2many("res.users", string="Default Approvers", domain="[('share', '=', False)]")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomApprovalRequest(models.Model):
    _name = "custom.approval.request"
    _description = "Multi-Step Approval Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Reference", readonly=True, copy=False, default="New")
    subject = fields.Char(required=True, tracking=True)
    category_id = fields.Many2one("custom.approval.category", required=True, tracking=True)
    request_owner_id = fields.Many2one("res.users", string="Requested By", default=lambda self: self.env.user, required=True)
    date_needed = fields.Date(string="Needed By")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    amount = fields.Monetary(string="Amount", tracking=True)
    reason = fields.Text(string="Business Justification")
    sale_order_id = fields.Many2one("sale.order", string="Related Sales Order")
    purchase_order_id = fields.Many2one("purchase.order", string="Related Purchase Order")
    account_move_id = fields.Many2one("account.move", string="Related Invoice / Bill")
    state = fields.Selection(
        [
            ("new", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("refused", "Refused"),
            ("cancel", "Cancelled"),
        ],
        default="new",
        tracking=True,
    )
    approver_ids = fields.One2many("custom.approval.approver", "request_id", string="Approvers")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.onchange("category_id")
    def _onchange_category_id(self):
        for req in self:
            if req.category_id and not req.approver_ids:
                req.approver_ids = [
                    Command.create({"user_id": user.id, "status": "new"})
                    for user in req.category_id.approver_ids
                ]

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.approval.request") or "APR"
            if vals.get("category_id") and not vals.get("approver_ids"):
                cat = self.env["custom.approval.category"].browse(vals["category_id"])
                if cat.approver_ids:
                    vals["approver_ids"] = [
                        Command.create({"user_id": u.id, "status": "new"}) for u in cat.approver_ids
                    ]
        return super().create(vals_list)

    def action_submit(self):
        for req in self:
            if not req.approver_ids:
                raise UserError(_("Add at least one approver before submitting."))
            req.approver_ids.write({"status": "pending"})
            req.state = "pending"
            req.message_post(body=_("Approval request submitted by %s.") % self.env.user.name)

    def _recompute_approval_state(self):
        for req in self:
            if any(a.status == "refused" for a in req.approver_ids):
                req.state = "refused"
            else:
                approved_count = len(req.approver_ids.filtered(lambda a: a.status == "approved"))
                needed = max(1, req.category_id.approval_minimum)
                if approved_count >= needed:
                    req.state = "approved"

    def action_approve_my_step(self):
        for req in self:
            my_lines = req.approver_ids.filtered(lambda a: a.user_id == self.env.user and a.status in ("new", "pending"))
            if not my_lines and self.env.is_superuser():
                my_lines = req.approver_ids.filtered(lambda a: a.status in ("new", "pending"))[:1]
            if not my_lines:
                raise UserError(_("You have no pending approval step on this request."))
            my_lines.write({"status": "approved", "decision_date": fields.Datetime.now()})
            req._recompute_approval_state()

    def action_refuse_my_step(self):
        for req in self:
            my_lines = req.approver_ids.filtered(lambda a: a.user_id == self.env.user and a.status in ("new", "pending"))
            if not my_lines and self.env.is_superuser():
                my_lines = req.approver_ids.filtered(lambda a: a.status in ("new", "pending"))[:1]
            if not my_lines:
                raise UserError(_("You have no pending approval step on this request."))
            my_lines.write({"status": "refused", "decision_date": fields.Datetime.now()})
            req._recompute_approval_state()

    def action_cancel(self):
        self.write({"state": "cancel"})


class CustomApprovalApprover(models.Model):
    _name = "custom.approval.approver"
    _description = "Approval Request Approver"
    _order = "id asc"

    request_id = fields.Many2one("custom.approval.request", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", required=True, domain="[('share', '=', False)]")
    status = fields.Selection(
        [("new", "New"), ("pending", "Pending"), ("approved", "Approved"), ("refused", "Refused")],
        default="new",
        required=True,
    )
    decision_date = fields.Datetime(readonly=True)
    comment = fields.Char()


class CustomDocumentFolder(models.Model):
    _name = "custom.document.folder"
    _description = "DMS Workspace Folder"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    parent_id = fields.Many2one("custom.document.folder", string="Parent Folder")
    description = fields.Char()
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomDocumentTag(models.Model):
    _name = "custom.document.tag"
    _description = "DMS Tag"
    _order = "name"

    name = fields.Char(required=True)
    color = fields.Integer(default=1)


class CustomDocument(models.Model):
    _name = "custom.document"
    _description = "Central Document Management Record"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Document Name", required=True, tracking=True)
    folder_id = fields.Many2one("custom.document.folder", string="Folder", required=True, tracking=True)
    tag_ids = fields.Many2many("custom.document.tag", string="Tags")
    owner_id = fields.Many2one("res.users", default=lambda self: self.env.user, tracking=True)
    partner_id = fields.Many2one("res.partner", string="Vendor / Customer")
    document_type = fields.Selection(
        [
            ("invoice_bill", "GST Invoice / Vendor Bill"),
            ("kyc_legal", "KYC / Legal / GSTIN"),
            ("brand_artwork", "Brand / Packaging Artwork"),
            ("tech_pack", "Garment / Gadget Tech Pack"),
            ("courier_manifest", "Courier / RTO Manifest"),
            ("other", "Other"),
        ],
        default="other",
        required=True,
    )
    version = fields.Char(default="1.0", tracking=True)
    expiry_date = fields.Date(string="Expiry / Renewal Date")
    file_data = fields.Binary(string="File", attachment=True)
    file_name = fields.Char(string="Filename")
    notes = fields.Text()
    vendor_bill_id = fields.Many2one("account.move", string="Linked Bill", readonly=True, copy=False)
    ticket_id = fields.Many2one("custom.support.ticket", string="Linked Ticket", readonly=True, copy=False)
    approval_id = fields.Many2one("custom.approval.request", string="Linked Approval", readonly=True, copy=False)
    sign_request_id = fields.Many2one("custom.sign.request", string="Linked e-Sign", readonly=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    def action_create_vendor_bill(self):
        self.ensure_one()
        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.partner_id.id if self.partner_id else False,
            "ref": self.name,
        })
        self.vendor_bill_id = bill.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": bill.id,
            "view_mode": "form",
        }

    def action_create_support_ticket(self):
        self.ensure_one()
        ticket = self.env["custom.support.ticket"].create({
            "subject": f"Document Review: {self.name}",
            "partner_id": self.partner_id.id if self.partner_id else False,
            "description": self.notes or self.name,
        })
        self.ticket_id = ticket.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "custom.support.ticket",
            "res_id": ticket.id,
            "view_mode": "form",
        }

    def action_request_approval(self):
        self.ensure_one()
        category = self.env["custom.approval.category"].search([], limit=1)
        if not category:
            raise UserError(_("Create at least one Approval Category first."))
        req = self.env["custom.approval.request"].create({
            "subject": f"Document Approval: {self.name}",
            "category_id": category.id,
            "reason": self.notes or self.name,
        })
        self.approval_id = req.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "custom.approval.request",
            "res_id": req.id,
            "view_mode": "form",
        }

    def action_send_for_signature(self):
        self.ensure_one()
        vals = {
            "subject": f"Sign: {self.name}",
            "document_pdf": self.file_data,
            "document_filename": self.file_name,
        }
        if self.partner_id:
            vals["signer_ids"] = [Command.create({"partner_id": self.partner_id.id})]
        sreq = self.env["custom.sign.request"].create(vals)
        self.sign_request_id = sreq.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "custom.sign.request",
            "res_id": sreq.id,
            "view_mode": "form",
        }

