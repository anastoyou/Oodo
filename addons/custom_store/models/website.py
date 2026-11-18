from lxml import etree

from odoo import api, fields, models


class Website(models.Model):
    _inherit = "website"

    x_store_code = fields.Char(
        string="Store Addon Code",
        copy=False,
        help="Technical slug linking this website to its custom_store_* addon views, SCSS, JS, and sync scripts.",
    )

    def _get_store_homepage_view(self):
        self.ensure_one()
        View = self.env["ir.ui.view"].with_context(active_test=False)
        view = View.search([
            ("key", "=", "website.homepage"),
            ("website_id", "=", self.id),
        ], limit=1)
        if not view:
            self._bootstrap_homepage()
            view = View.search([
                ("key", "=", "website.homepage"),
                ("website_id", "=", self.id),
            ], limit=1)
        return view

    def _apply_store_homepage_template(self, template_xmlid, force=False):
        """Seed or update this website's Builder-editable homepage from a QWeb template in addons/."""
        self.ensure_one()
        tmpl = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not tmpl:
            return False
        homepage_view = self._get_store_homepage_view()
        if not homepage_view:
            return False
        if not force:
            current_arch = homepage_view.arch_db or ""
            if "oe_empty" not in current_arch and current_arch.strip():
                return False

        root = etree.fromstring(tmpl.arch_db.encode("utf-8"))
        root.set("t-name", "website.homepage")
        root.set("name", "Homepage")
        new_arch = etree.tostring(root, encoding="unicode")
        homepage_view.with_context(no_cow=True).write({"arch_db": new_arch})
        return True

    def _apply_store_footer_template(self, template_xmlid, force=False):
        """Seed or update this website's Builder-editable footer (website.footer_custom CoW copy)."""
        self.ensure_one()
        tmpl = self.env.ref(template_xmlid, raise_if_not_found=False)
        base_footer = self.env.ref("website.footer_custom", raise_if_not_found=False)
        if not tmpl or not base_footer:
            return False

        View = self.env["ir.ui.view"].with_context(active_test=False)
        spec_footer = View.search([
            ("key", "=", base_footer.key),
            ("website_id", "=", self.id),
        ], limit=1)
        if spec_footer and not force:
            return False

        tmpl_root = etree.fromstring(tmpl.arch_db.encode("utf-8"))
        footer_div = tmpl_root if tmpl_root.tag == "div" else tmpl_root.find(".//div[@id='footer']")
        if footer_div is None:
            return False

        wrapper = etree.Element("data")
        xpath_el = etree.SubElement(wrapper, "xpath", expr="//div[@id='footer']", position="replace")
        xpath_el.append(footer_div)
        new_arch = etree.tostring(wrapper, encoding="unicode")

        base_footer.with_context(website_id=self.id).write({
            "active": True,
            "arch_db": new_arch,
        })
        return True

    @api.model
    def _ensure_custom_store_isolation(self):
        """Isolate custom_store Website 1 views/assets so new websites never inherit custom_store content."""
        default_site = self.search([("x_store_code", "=", "custom_store")], limit=1) or self.search([], order="id", limit=1)
        if not default_site:
            return

        if not default_site.x_store_code:
            default_site.x_store_code = "custom_store"

        View = self.env["ir.ui.view"].with_context(active_test=False, no_cow=True)

        # Clean up legacy generic homepage/footer inheritance if present from earlier installs
        legacy_views = View.search([
            ("key", "in", ("custom_store.homepage_custom", "custom_store.footer_custom")),
        ])
        had_legacy_homepage = any(v.key == "custom_store.homepage_custom" for v in legacy_views)
        had_legacy_footer = any(v.key == "custom_store.footer_custom" for v in legacy_views)
        if legacy_views:
            legacy_views.unlink()

        default_site._apply_store_homepage_template(
            "custom_store.homepage_custom_tmpl",
            force=had_legacy_homepage,
        )
        default_site._apply_store_footer_template(
            "custom_store.footer_custom_tmpl",
            force=had_legacy_footer,
        )

        # Scope custom_store apparel policy pages to Website 1 if they are currently global
        Page = self.env["website.page"].with_context(active_test=False)
        for xmlid in (
            "custom_store.page_size_guide",
            "custom_store.page_shipping_policy",
            "custom_store.page_return_policy",
        ):
            page = self.env.ref(xmlid, raise_if_not_found=False)
            if page and not page.website_id:
                page.write({"website_id": default_site.id})
                if page.view_id and not page.view_id.website_id:
                    page.view_id.with_context(no_cow=True).write({"website_id": default_site.id})

        # Scope custom_store primary variables, SCSS, and JS assets strictly to Website 1
        Asset = self.env["ir.asset"].with_context(active_test=False, no_cow=True)
        asset_specs = [
            {
                "name": "Custom Store Primary Variables",
                "bundle": "web._assets_primary_variables",
                "directive": "before",
                "target": "website/static/src/scss/options/user_values.scss",
                "path": "custom_store/static/src/scss/primary_variables.scss",
            },
            {
                "name": "Custom Store Frontend SCSS",
                "bundle": "web.assets_frontend",
                "directive": "append",
                "target": False,
                "path": "custom_store/static/src/scss/custom_store.scss",
            },
            {
                "name": "Custom Store Frontend JS",
                "bundle": "web.assets_frontend",
                "directive": "append",
                "target": False,
                "path": "custom_store/static/src/js/custom_store.js",
            },
        ]
        stale_global_assets = Asset.search([
            ("website_id", "=", False),
            ("path", "in", [s["path"] for s in asset_specs]),
        ])
        if stale_global_assets:
            stale_global_assets.unlink()
        for spec in asset_specs:
            existing = Asset.search([
                ("website_id", "=", default_site.id),
                ("path", "=", spec["path"]),
            ], limit=1)
            if not existing:
                Asset.create({**spec, "website_id": default_site.id, "active": True})
