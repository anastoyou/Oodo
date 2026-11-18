import logging
from urllib.parse import quote_plus

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CustomInstagramProductSync(models.Model):
    _name = "custom.instagram.product.sync"
    _description = "Unit Product to Instagram Direct-Link Sync"
    _order = "id desc"

    _uniq_account_product = models.Constraint(
        "unique(account_id, product_tmpl_id)",
        "Each unit Instagram account can have only one sync record per product.",
    )

    name = fields.Char(related="product_tmpl_id.name", string="Product")
    account_id = fields.Many2one("custom.instagram.account", string="Unit Instagram Account", required=True, ondelete="cascade")
    website_id = fields.Many2one(related="account_id.website_id", string="Business Unit (Website)", store=True)
    product_tmpl_id = fields.Many2one("product.template", string="Product Template", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="product_tmpl_id.currency_id")
    list_price = fields.Float(related="product_tmpl_id.list_price", string="Sale Price")

    keyword_code = fields.Char(string="DM Keyword / Code", index=True)
    direct_shop_url = fields.Char(string="Direct Checkout URL", compute="_compute_urls")
    tracked_dm_url = fields.Char(string="Tracked DM Short Link", compute="_compute_urls")
    public_image_url = fields.Char(string="Product Image URL", compute="_compute_urls")

    caption = fields.Text(string="Instagram Post / DM Caption")
    ig_creation_id = fields.Char(string="IG Container ID", readonly=True)
    ig_media_id = fields.Char(string="IG Media ID", readonly=True)
    ig_permalink = fields.Char(string="IG Post URL", readonly=True)

    sync_state = fields.Selection(
        [
            ("pending", "Pending Sync"),
            ("ready", "Synced (DM Link Ready)"),
            ("published", "Published to IG Feed"),
            ("error", "Sync Error"),
        ],
        default="pending",
        required=True,
    )
    last_synced_at = fields.Datetime(string="Last Synced At", readonly=True)
    last_error = fields.Text(string="Sync Notes / Error", readonly=True)

    dm_sent_count = fields.Integer(string="DMs Sent", default=0, readonly=True)
    dm_click_count = fields.Integer(string="DM Link Clicks", default=0, readonly=True)

    def _compute_urls(self):
        fallback_base = (
            self.env["ir.config_parameter"].sudo().get_str("web.base.url")
            or self.env["custom.instagram.account"]._read_env_setting("ODOO_URL")
        ).rstrip("/")
        for rec in self:
            base = rec.account_id._unit_base_url() if rec.account_id else fallback_base
            tmpl = rec.product_tmpl_id
            path = (tmpl.website_url or f"/shop/{tmpl.id}") if tmpl else "/shop"
            if not path.startswith("/"):
                path = f"/{path}"
            utm_camp = quote_plus(rec.account_id.default_utm_campaign or "ig_dm_link")
            utm_kw = quote_plus(rec.keyword_code or f"BUY{tmpl.id if tmpl else 0}")
            sep = "&" if "?" in path else "?"
            rec.direct_shop_url = f"{base}{path}{sep}utm_source=instagram&utm_medium=dm&utm_campaign={utm_camp}&utm_content={utm_kw}"
            rec.tracked_dm_url = f"{base}/ig/go/{rec.id}" if rec.id else rec.direct_shop_url
            rec.public_image_url = f"{base}/ig/img/{tmpl.id}.jpg" if (tmpl and tmpl.image_1920) else False

    def _default_keyword(self, tmpl):
        if tmpl.x_ig_dm_keyword:
            return tmpl.x_ig_dm_keyword.strip().upper()
        if tmpl.default_code:
            return tmpl.default_code.strip().upper()
        return f"BUY{tmpl.id}"

    def _default_caption(self, tmpl, keyword):
        symbol = tmpl.currency_id.symbol or "₹"
        return (
            f"{tmpl.name} — {symbol}{tmpl.list_price:,.0f}\n"
            f"Comment '{keyword}' or DM '{keyword}' now and receive the direct checkout link instantly!"
        )

    def action_sync_now(self, publish_feed=False):
        for rec in self:
            tmpl = rec.product_tmpl_id
            kw = rec.keyword_code or rec._default_keyword(tmpl)
            caption = rec.caption or rec._default_caption(tmpl, kw)
            updates = {
                "keyword_code": kw,
                "caption": caption,
                "last_synced_at": fields.Datetime.now(),
                "last_error": False,
            }

            acc = rec.account_id
            if acc.auto_publish_to_feed or publish_feed:
                img_url = rec.public_image_url
                is_public_https = bool(img_url and img_url.startswith("https://") and not img_url.startswith("https://localhost"))
                if acc.sandbox_mode:
                    updates["sync_state"] = "published"
                    updates["ig_media_id"] = rec.ig_media_id or f"sim_media_{rec.id}"
                elif not (acc.access_token and acc.ig_user_id):
                    msg = _("Connect an Instagram Login token and IG User ID on account '%s' before publishing to Feed.") % acc.name
                    if publish_feed:
                        raise UserError(msg)
                    updates["sync_state"] = "ready"
                    updates["last_error"] = msg
                elif not is_public_https:
                    msg = _(
                        "Upload a product image and ensure a public HTTPS URL is configured (current image URL: %s)."
                    ) % (img_url or "missing")
                    if publish_feed:
                        raise UserError(msg)
                    updates["sync_state"] = "ready"
                    updates["last_error"] = msg
                else:
                    ok_c, c_data = acc._graph_request(
                        "POST",
                        f"{acc.ig_user_id}/media",
                        params={"image_url": img_url, "caption": caption},
                    )
                    creation_id = c_data.get("id") if ok_c else False
                    if not ok_c or not creation_id:
                        updates["sync_state"] = "error"
                        updates["last_error"] = (c_data.get("error") or {}).get("message") or str(c_data)
                    else:
                        updates["ig_creation_id"] = creation_id
                        ok_p, p_data = acc._graph_request(
                            "POST",
                            f"{acc.ig_user_id}/media_publish",
                            params={"creation_id": creation_id},
                        )
                        if ok_p and p_data.get("id"):
                            updates["ig_media_id"] = p_data["id"]
                            updates["sync_state"] = "published"
                        else:
                            updates["sync_state"] = "error"
                            updates["last_error"] = (p_data.get("error") or {}).get("message") or str(p_data)
            else:
                updates["sync_state"] = "ready"

            rec.write(updates)
        return True

    def action_publish_to_feed(self):
        self.action_sync_now(publish_feed=True)
        failed = self.filtered(lambda s: s.sync_state == "error")
        if failed:
            raise UserError(failed[0].last_error or _("Instagram Feed publish failed."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Instagram Feed Publish"),
                "message": _("Published %s product post(s) to Instagram Feed.") % len(self),
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_send_dm_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Send Direct Product Link DM"),
            "res_model": "custom.instagram.send.link.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_account_id": self.account_id.id,
                "default_product_sync_id": self.id,
            },
        }

    @api.model
    def sync_products_for_account(self, account, products):
        synced = self.browse()
        for tmpl in products:
            if not tmpl.sale_ok:
                continue
            existing = self.search([("account_id", "=", account.id), ("product_tmpl_id", "=", tmpl.id)], limit=1)
            kw = existing._default_keyword(tmpl) if existing else (tmpl.x_ig_dm_keyword or tmpl.default_code or f"BUY{tmpl.id}").strip().upper()
            cap = f"{tmpl.name} — {tmpl.currency_id.symbol or '₹'}{tmpl.list_price:,.0f}\nComment '{kw}' or DM '{kw}' for the direct checkout link!"
            if existing:
                existing.write({"keyword_code": kw, "caption": cap})
                rec = existing
            else:
                rec = self.create({
                    "account_id": account.id,
                    "product_tmpl_id": tmpl.id,
                    "keyword_code": kw,
                    "caption": cap,
                })
            try:
                rec.action_sync_now()
            except Exception as exc:
                _logger.warning("Instagram sync skipped for %s on unit %s: %s", tmpl.display_name, account.name, exc)
                rec.write({"sync_state": "error", "last_error": str(exc)})
            synced |= rec
        return synced

    @api.model
    def sync_product_across_matching_units(self, products, force_manual=False):
        Account = self.env["custom.instagram.account"].sudo()
        acc_domain = [("active", "=", True)]
        if not force_manual:
            acc_domain.append(("auto_sync_new_products", "=", True))
        active_accounts = Account.search(acc_domain)
        synced = self.browse()
        for tmpl in products:
            if not force_manual and (not tmpl.sale_ok or not tmpl.x_ig_auto_sync):
                continue
            if tmpl.website_id:
                target_accs = active_accounts.filtered(lambda a: a.website_id == tmpl.website_id)
            else:
                target_accs = active_accounts if force_manual else active_accounts.filtered(lambda a: a.sync_shared_products)
            if force_manual and not target_accs:
                unit_label = tmpl.website_id.name if tmpl.website_id else _("any Website")
                raise UserError(_(
                    "No active Instagram Business account found for unit '%s'. "
                    "Create one under Instagram DM -> Units, Credentials & Webhooks -> Unit Accounts & Tokens."
                ) % unit_label)
            for acc in target_accs:
                if not force_manual and tmpl.type == "service" and not acc.sync_service_products:
                    continue
                synced |= self.sudo().sync_products_for_account(acc, tmpl)
        return synced


class ProductTemplateInstagram(models.Model):
    _inherit = "product.template"

    x_ig_auto_sync = fields.Boolean(
        string="Auto-Sync to Unit Instagram",
        default=True,
        help="Automatically creates & updates DM Direct-Link sync entries when this product is added or updated in a Business Unit.",
    )
    x_ig_dm_keyword = fields.Char(
        string="Instagram DM / Comment Keyword",
        help="Optional short keyword customers comment or DM to get this product link (defaults to SKU or BUY<id>).",
    )
    x_ig_sync_ids = fields.One2many("custom.instagram.product.sync", "product_tmpl_id", string="Unit Instagram Syncs")
    x_ig_sync_count = fields.Integer(string="IG Syncs", compute="_compute_x_ig_sync_count")

    @api.depends("x_ig_sync_ids")
    def _compute_x_ig_sync_count(self):
        for rec in self:
            rec.x_ig_sync_count = len(rec.x_ig_sync_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env["custom.instagram.product.sync"].sync_product_across_matching_units(records)
        return records

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = {"name", "list_price", "default_code", "website_id", "is_published", "sale_ok", "x_ig_auto_sync", "x_ig_dm_keyword"}
        if trigger_fields & set(vals.keys()):
            self.env["custom.instagram.product.sync"].sync_product_across_matching_units(self)
        return res

    def action_sync_to_instagram(self):
        synced = self.env["custom.instagram.product.sync"].sync_product_across_matching_units(self, force_manual=True)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Instagram Sync Complete"),
                "message": _("Synced to %s Unit Instagram record(s). Direct DM link is ready.") % len(synced),
                "type": "success",
                "sticky": False,
            },
        }

    def action_publish_ig_feed(self):
        synced = self.env["custom.instagram.product.sync"].sync_product_across_matching_units(self, force_manual=True)
        return synced.action_publish_to_feed()

    def action_view_ig_syncs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Instagram Unit Syncs"),
            "res_model": "custom.instagram.product.sync",
            "view_mode": "list,form",
            "domain": [("product_tmpl_id", "=", self.id)],
            "context": {"default_product_tmpl_id": self.id},
        }

    def action_open_send_ig_dm(self):
        self.ensure_one()
        sync = self.x_ig_sync_ids[:1]
        return {
            "type": "ir.actions.act_window",
            "name": _("Send Direct Product Link DM"),
            "res_model": "custom.instagram.send.link.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_account_id": sync.account_id.id if sync else False,
                "default_product_sync_id": sync.id if sync else False,
            },
        }
