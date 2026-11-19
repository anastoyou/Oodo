import json
import logging
import re
import shutil
from pathlib import Path

from odoo import api, fields, models

_logger = logging.getLogger(__name__)
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_FEATURES_BLOCK_RE = re.compile(
    r"export const DETECTED_ODOO_FEATURES\s*=\s*\{.*?\};",
    re.DOTALL,
)


class CustomStoreProductPdp(models.Model):
    _name = "custom.store.product.pdp"
    _description = "Custom Per-Website Product Detail Page"
    _order = "website_id, product_tmpl_id, id"

    name = fields.Char(string="Folder Name", required=True, index=True)
    website_id = fields.Many2one(
        comodel_name="website",
        string="Website",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_tmpl_id = fields.Many2one(
        comodel_name="product.template",
        string="Product",
        required=True,
        ondelete="cascade",
        index=True,
    )
    store_code = fields.Char(
        string="Store Code",
        related="website_id.x_store_code",
        store=True,
        readonly=True,
    )
    addon_name = fields.Char(string="Addon Module", required=True)
    folder_name = fields.Char(string="PDP Folder", required=True)
    mode = fields.Selection(
        selection=[
            ("native", "Native with Page Builder"),
            ("react", "React + Tailwind CSS"),
        ],
        string="Code Type",
        required=True,
        default="native",
    )
    template_key = fields.Char(
        string="Native QWeb Template Key",
        help="Key of the website-scoped ir.ui.view rendered when Code Type is Native.",
    )
    view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        string="Native QWeb View",
        ondelete="set null",
    )
    bundle_js = fields.Char(
        string="React JS URL",
        help="Static URL for the compiled customer-facing Vite React bundle (PdpPage.tsx).",
    )
    bundle_css = fields.Char(
        string="React CSS URL",
        help="Static URL for the compiled Tailwind CSS bundle.",
    )
    bundle_full_js = fields.Char(
        string="Dev Full-Data JS URL",
        help="Static URL for developer-only pdppage_full_data.tsx preview (?pdp_dev=full).",
    )
    bundle_full_css = fields.Char(
        string="Dev Full-Data CSS URL",
        help="Static URL for developer-only pdppage_full_data.tsx CSS.",
    )
    active = fields.Boolean(
        string="Enabled",
        default=True,
        help="Turn OFF to temporarily show Odoo's default product page while keeping your custom code files on disk.",
    )
    status = fields.Selection(
        selection=[
            ("active", "Active (Custom UI)"),
            ("paused", "Off (Default Odoo Page)"),
        ],
        string="Status",
        compute="_compute_status",
    )

    @api.depends("active")
    def _compute_status(self):
        for rec in self:
            rec.status = "active" if rec.active else "paused"

    def action_delete_with_code(self):
        """Permanently delete custom PDP override(s), QWeb view(s), and disk code folders."""
        from_product_form = bool(self.env.context.get("from_product_form"))
        self.unlink()
        if from_product_form:
            return {"type": "ir.actions.client", "tag": "soft_reload"}
        return self.env["ir.actions.act_window"]._for_xml_id(
            "custom_store.action_custom_store_product_pdp"
        )

    _unique_website_product = models.Constraint(
        "unique (website_id, product_tmpl_id)",
        "Only one custom PDP mapping per website and product is allowed.",
    )

    @api.model
    def _get_repo_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @api.model
    def _get_addons_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @api.model
    def _is_safe_addon_and_folder(self, addon_name: str, folder_name: str) -> bool:
        return bool(
            addon_name
            and folder_name
            and addon_name.startswith("custom_store")
            and _SAFE_SEGMENT_RE.fullmatch(addon_name)
            and _SAFE_SEGMENT_RE.fullmatch(folder_name)
        )

    @api.model
    def _cleanup_disk_artifacts(self, targets: list[tuple[str, str]]) -> None:
        """Delete custom_pdp/<folder> and compiled static/dist/pdp_<folder> folders safely."""
        addons_root = self._get_addons_root().resolve()
        for addon_name, folder_name in set(targets):
            if not self._is_safe_addon_and_folder(addon_name, folder_name):
                _logger.warning(
                    "Skipping unsafe custom PDP cleanup path: addon=%r folder=%r",
                    addon_name,
                    folder_name,
                )
                continue

            addon_dir = (addons_root / addon_name).resolve()
            if addon_dir.parent != addons_root or not addon_dir.is_dir():
                continue

            candidates = [
                addon_dir / "custom_pdp" / folder_name,
                addon_dir / "static" / "dist" / f"pdp_{folder_name}",
            ]
            for target_dir in candidates:
                resolved = target_dir.resolve()
                if addon_dir not in resolved.parents:
                    continue
                if resolved.exists() and resolved.is_dir():
                    try:
                        shutil.rmtree(resolved)
                        _logger.info("Deleted custom PDP directory: %s", resolved)
                    except OSError:
                        _logger.exception("Failed deleting custom PDP directory: %s", resolved)

    def _schedule_cleanup_on_commit(self, targets: list[tuple[str, str]]) -> None:
        clean_targets = [
            (addon, folder)
            for addon, folder in targets
            if self._is_safe_addon_and_folder(addon, folder)
        ]
        if clean_targets:
            self.env.cr.postcommit.add(
                lambda t=clean_targets: self.env["custom.store.product.pdp"]._cleanup_disk_artifacts(t)
            )

    def _collect_feature_snapshot(self) -> dict:
        """Collect live product & website feature/media metadata for developer reference."""
        self.ensure_one()
        product = self.product_tmpl_id.sudo()
        website = self.website_id.sudo()
        variant = product.product_variant_id

        extra_images = product.product_template_image_ids
        video_urls = [img.video_url for img in extra_images if img.video_url]
        media_urls = [
            f"/web/image/{img._name}/{img.id}/image_1024"
            for img in (variant._get_images() if variant else product._get_images())
        ]
        docs = (
            product._get_product_page_documents(variant=variant)
            if hasattr(product, "_get_product_page_documents")
            else self.env["product.document"]
        )
        tags = (
            variant.all_product_tag_ids.filtered("visible_to_customers")
            if variant
            else product.product_tag_ids.filtered("visible_to_customers")
        )
        ribbon = (
            product._get_ribbon(variant=variant)
            if hasattr(product, "_get_ribbon")
            else False
        )
        alt_products = (
            product._get_website_alternative_product()
            if hasattr(product, "_get_website_alternative_product")
            else self.env["product.template"]
        )
        acc_products = (
            product._get_website_accessory_product()
            if hasattr(product, "_get_website_accessory_product")
            else self.env["product.product"]
        )
        opt_products = getattr(product, "optional_product_ids", self.env["product.template"])
        uoms = product._get_available_uoms() if hasattr(product, "_get_available_uoms") else self.env["uom.uom"]

        return {
            "website_id": website.id,
            "website_name": website.name,
            "product_id": product.id,
            "product_name": product.name,
            "default_code": product.default_code or "",
            "is_published": bool(product.is_published),
            "media_images_count": len(media_urls),
            "media_urls": media_urls,
            "video_urls": video_urls,
            "variant_attributes": [
                {
                    "attribute": ptal.attribute_id.name,
                    "display_type": ptal.attribute_id.display_type,
                    "values": ptal.product_template_value_ids._only_active().mapped("name"),
                }
                for ptal in product.valid_product_template_attribute_line_ids
            ],
            "ribbon": ribbon.name if ribbon else None,
            "tags": tags.mapped("name"),
            "documents": docs.mapped("name"),
            "optional_products": opt_products.mapped("name"),
            "accessory_products": acc_products.mapped("display_name"),
            "alternative_products": alt_products.mapped("name"),
            "uoms": uoms.mapped("name"),
            "is_storable": bool(product.is_storable),
            "allow_out_of_stock_order": bool(product.allow_out_of_stock_order),
            "show_availability": bool(product.show_availability),
            "compare_list_price": float(getattr(product, "compare_list_price", 0.0) or 0.0),
            "website_options": {
                "show_quantity": bool(website.is_view_active("website_sale.product_quantity")),
                "buy_now_enabled": bool(website.is_view_active("website_sale.product_buy_now")),
                "wishlist_enabled": bool(
                    "product.wishlist" in self.env
                    and website.is_view_active("website_sale.product_add_to_wishlist")
                ),
                "compare_enabled": bool(
                    website.is_view_active("website_sale.product_add_to_compare")
                ),
                "reviews_enabled": bool(
                    website.is_view_active("website_sale.product_comment")
                ),
                "tax_indication_enabled": bool(
                    website.is_view_active("website_sale.tax_indication")
                ),
            },
            "specs": {
                "x_fabric": getattr(product, "x_fabric", False) or "",
                "x_fit_type": getattr(product, "x_fit_type", False) or "",
                "x_wash_care": getattr(product, "x_wash_care", False) or "",
                "x_dispatch_days": getattr(product, "x_dispatch_days", False) or 0,
            },
        }

    def sync_full_data_file(self) -> None:
        """Create or update react/pdppage_full_data.tsx with current product/website options."""
        addons_root = self._get_addons_root().resolve()
        template_path = self._get_repo_root() / "frontend_pdp" / "src" / "DefaultPdpFullDataTemplate.tsx"
        if not template_path.is_file():
            _logger.warning("DefaultPdpFullDataTemplate.tsx not found at %s", template_path)
            return

        base_template = template_path.read_text(encoding="utf-8")
        for rec in self.sudo().with_context(active_test=False):
            if rec.mode != "react" or not rec._is_safe_addon_and_folder(rec.addon_name, rec.folder_name):
                continue
            if not rec.product_tmpl_id.exists() or not rec.website_id.exists():
                continue

            addon_dir = (addons_root / rec.addon_name).resolve()
            if not addon_dir.is_dir():
                continue
            react_dir = addon_dir / "custom_pdp" / rec.folder_name / "react"
            if not react_dir.is_dir():
                continue

            snapshot = rec._collect_feature_snapshot()
            features_block = (
                "export const DETECTED_ODOO_FEATURES = "
                + json.dumps(snapshot, indent=2, ensure_ascii=False)
                + ";"
            )
            full_data_path = react_dir / "pdppage_full_data.tsx"
            source_text = (
                full_data_path.read_text(encoding="utf-8")
                if full_data_path.is_file()
                else base_template
            )
            if _FEATURES_BLOCK_RE.search(source_text):
                updated_text = _FEATURES_BLOCK_RE.sub(
                    lambda _m: features_block,
                    source_text,
                    count=1,
                )
            else:
                updated_text = _FEATURES_BLOCK_RE.sub(
                    lambda _m: features_block,
                    base_template,
                    count=1,
                )

            if not full_data_path.is_file() or full_data_path.read_text(encoding="utf-8") != updated_text:
                full_data_path.write_text(updated_text, encoding="utf-8")
                _logger.info("Synced developer reference file: %s", full_data_path)

    @api.model
    def _schedule_full_data_sync_for_products(self, product_tmpl_ids: list[int]) -> None:
        if not product_tmpl_ids:
            return
        pdp_ids = (
            self.sudo()
            .with_context(active_test=False)
            .search([("product_tmpl_id", "in", list(set(product_tmpl_ids))), ("mode", "=", "react")])
            .ids
        )
        if pdp_ids:
            self.env.cr.postcommit.add(
                lambda ids=pdp_ids: self._run_postcommit_full_data_sync(ids)
            )

    @api.model
    def _schedule_full_data_sync_for_all_react(self) -> None:
        pdp_ids = (
            self.sudo()
            .with_context(active_test=False)
            .search([("mode", "=", "react")])
            .ids
        )
        if pdp_ids:
            self.env.cr.postcommit.add(
                lambda ids=pdp_ids: self._run_postcommit_full_data_sync(ids)
            )

    @api.model
    def _run_postcommit_full_data_sync(self, pdp_ids: list[int]) -> None:
        try:
            with self.env.registry.cursor() as new_cr:
                new_env = api.Environment(new_cr, self.env.uid, self.env.context)
                recs = new_env["custom.store.product.pdp"].sudo().browse(pdp_ids).exists()
                if recs:
                    recs.sync_full_data_file()
        except Exception:
            _logger.exception("Failed postcommit sync of pdppage_full_data.tsx for %s", pdp_ids)

    def unlink(self):
        targets = [(rec.addon_name, rec.folder_name) for rec in self if rec.addon_name and rec.folder_name]
        views = self.mapped("view_id").exists()
        res = super().unlink()
        if views:
            views.sudo().with_context(no_cow=True).unlink()
        self._schedule_cleanup_on_commit(targets)
        return res

    @api.model
    def register_pdp(
        self,
        website_id: int,
        product_tmpl_id: int,
        addon_name: str,
        folder_name: str,
        mode: str,
        template_key: str | None = None,
        xml_arch: str | None = None,
        bundle_js: str | None = None,
        bundle_css: str | None = None,
        bundle_full_js: str | None = None,
        bundle_full_css: str | None = None,
        preserve_active: bool = False,
    ):
        """Create or update a per-(website, product) custom PDP mapping and optional QWeb view."""
        website = self.env["website"].sudo().browse(website_id)
        product = self.env["product.template"].sudo().browse(product_tmpl_id)
        if not website.exists() or not product.exists():
            raise ValueError(f"Invalid website ({website_id}) or product ({product_tmpl_id}).")

        existing = self.sudo().with_context(active_test=False).search([
            ("website_id", "=", website.id),
            ("product_tmpl_id", "=", product.id),
        ], limit=1)

        view = existing.view_id if existing else self.env["ir.ui.view"]
        if mode == "native":
            if not template_key or not xml_arch:
                raise ValueError("Native PDP registration requires template_key and xml_arch.")
            View = self.env["ir.ui.view"].sudo().with_context(no_cow=True)
            if not view:
                view = View.search([
                    ("key", "=", template_key),
                    ("website_id", "=", website.id),
                ], limit=1)
            view_vals = {
                "name": f"{product.display_name} Custom PDP ({website.name})",
                "type": "qweb",
                "key": template_key,
                "website_id": website.id,
                "arch_db": xml_arch,
                "active": True,
            }
            if view:
                view.write(view_vals)
            else:
                view = View.create(view_vals)
        elif view:
            old_view = view
            view = self.env["ir.ui.view"]
            old_view.sudo().with_context(no_cow=True).unlink()

        vals = {
            "name": folder_name,
            "website_id": website.id,
            "product_tmpl_id": product.id,
            "addon_name": addon_name,
            "folder_name": folder_name,
            "mode": mode,
            "template_key": template_key if mode == "native" else False,
            "view_id": view.id if view else False,
            "bundle_js": bundle_js if mode == "react" else False,
            "bundle_css": bundle_css if mode == "react" else False,
            "bundle_full_js": bundle_full_js if mode == "react" else False,
            "bundle_full_css": bundle_full_css if mode == "react" else False,
        }
        if not (existing and preserve_active):
            vals["active"] = True
        if existing:
            old_targets = []
            if existing.folder_name != folder_name or existing.addon_name != addon_name:
                old_targets.append((existing.addon_name, existing.folder_name))
            existing.sudo().write(vals)
            if old_targets:
                self._schedule_cleanup_on_commit(old_targets)
            record = existing
        else:
            record = self.sudo().create(vals)

        if mode == "react":
            record.sync_full_data_file()
        return record.id


class ProductTemplate(models.Model):
    _inherit = "product.template"

    custom_pdp_ids = fields.One2many(
        comodel_name="custom.store.product.pdp",
        inverse_name="product_tmpl_id",
        string="Custom PDPs",
        context={"active_test": False},
    )
    custom_pdp_count = fields.Integer(
        string="Custom PDP Count",
        compute="_compute_custom_pdp_count",
    )

    @api.depends("custom_pdp_ids", "custom_pdp_ids.active")
    def _compute_custom_pdp_count(self):
        counts = dict(
            self.env["custom.store.product.pdp"]
            .with_context(active_test=False)
            ._read_group(
                [("product_tmpl_id", "in", self.ids)],
                ["product_tmpl_id"],
                ["__count"],
            )
        )
        for product in self:
            product.custom_pdp_count = counts.get(product, 0)

    def write(self, vals):
        res = super().write(vals)
        self.env["custom.store.product.pdp"]._schedule_full_data_sync_for_products(self.ids)
        return res

    def unlink(self):
        # PostgreSQL ON DELETE CASCADE skips Python unlink() on custom.store.product.pdp,
        # so snapshot disk folders and QWeb views before super().unlink().
        CustomPdp = self.env["custom.store.product.pdp"].sudo().with_context(active_test=False)
        pdp_records = CustomPdp.search([("product_tmpl_id", "in", self.ids)])
        targets = [
            (rec.addon_name, rec.folder_name)
            for rec in pdp_records
            if rec.addon_name and rec.folder_name
        ]
        views = pdp_records.mapped("view_id").exists()

        res = super().unlink()

        if views:
            views.sudo().with_context(no_cow=True).unlink()
        if targets:
            CustomPdp._schedule_cleanup_on_commit(targets)
        return res


class ProductImage(models.Model):
    _inherit = "product.image"

    def _collect_tmpl_ids(self) -> list[int]:
        tmpl_ids = list(self.mapped("product_tmpl_id").ids)
        if "product_variant_id" in self._fields:
            tmpl_ids += self.mapped("product_variant_id.product_tmpl_id").ids
        return tmpl_ids

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env["custom.store.product.pdp"]._schedule_full_data_sync_for_products(
            records._collect_tmpl_ids()
        )
        return records

    def write(self, vals):
        tmpl_ids = self._collect_tmpl_ids()
        res = super().write(vals)
        tmpl_ids += self._collect_tmpl_ids()
        self.env["custom.store.product.pdp"]._schedule_full_data_sync_for_products(tmpl_ids)
        return res

    def unlink(self):
        tmpl_ids = self._collect_tmpl_ids()
        res = super().unlink()
        self.env["custom.store.product.pdp"]._schedule_full_data_sync_for_products(tmpl_ids)
        return res


class ProductTemplateAttributeLine(models.Model):
    _inherit = "product.template.attribute.line"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env["custom.store.product.pdp"]._schedule_full_data_sync_for_products(
            records.mapped("product_tmpl_id").ids
        )
        return records

    def write(self, vals):
        tmpl_ids = self.mapped("product_tmpl_id").ids
        res = super().write(vals)
        tmpl_ids += self.mapped("product_tmpl_id").ids
        self.env["custom.store.product.pdp"]._schedule_full_data_sync_for_products(tmpl_ids)
        return res

    def unlink(self):
        tmpl_ids = self.mapped("product_tmpl_id").ids
        res = super().unlink()
        self.env["custom.store.product.pdp"]._schedule_full_data_sync_for_products(tmpl_ids)
        return res


class IrUiViewPdpSync(models.Model):
    _inherit = "ir.ui.view"

    def write(self, vals):
        has_wsale_feature = "active" in vals and any(
            v.key and v.key.startswith("website_sale.") for v in self
        )
        res = super().write(vals)
        if has_wsale_feature:
            self.env["custom.store.product.pdp"]._schedule_full_data_sync_for_all_react()
        return res
