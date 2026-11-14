from odoo import _, api, fields, models

APPAREL_HSN_PREFIXES = ("61", "62", "63", "5407", "5208", "64")
GST_LOW_SLAB_LIMIT = 2500.0


class ProductTemplate(models.Model):
    _inherit = "product.template"

    x_fabric = fields.Char(
        string="Fabric / Material",
        help="e.g. Pure Cotton, Rayon 14kg, Chanderi Silk",
    )
    x_fit_type = fields.Selection(
        selection=[
            ("regular", "Regular Fit"),
            ("relaxed", "Relaxed / A-Line"),
            ("slim", "Slim Fit"),
            ("oversized", "Oversized"),
            ("unstitched", "Unstitched / Cut Piece"),
        ],
        string="Fit / Cut",
        default="regular",
    )
    x_wash_care = fields.Text(
        string="Care Instructions",
        default="Gentle machine or hand wash in cold water. Dry in shade.",
        help="Displayed on product pages and garment hang-tag specifications.",
    )
    x_dispatch_days = fields.Integer(
        string="Dispatch Lead Time (Days)",
        default=2,
        help="Estimated dispatch window shown to storefront buyers.",
    )
    x_gst_slab_warning = fields.Char(
        string="GST Slab Advisory",
        compute="_compute_x_gst_slab_warning",
    )

    @staticmethod
    def _effective_tax_rate(tax):
        """Return summed percentage rate for simple or GST tax-group taxes."""
        if tax.amount_type == "group":
            return sum(child.amount for child in tax.children_tax_ids if child.amount_type == "percent")
        return tax.amount if tax.amount_type == "percent" else 0.0

    @api.depends("list_price", "taxes_id", "taxes_id.amount", "l10n_in_hsn_code", "sale_ok")
    def _compute_x_gst_slab_warning(self):
        company = self.env.company
        is_india = company.country_id.code == "IN"
        for tmpl in self:
            warning = False
            if is_india and tmpl.sale_ok:
                hsn = (tmpl.l10n_in_hsn_code or "").strip()
                is_apparel_hsn = not hsn or hsn.startswith(APPAREL_HSN_PREFIXES)
                company_taxes = tmpl.taxes_id.filtered(lambda t: t.company_id in (company, False))
                rate = sum(tmpl._effective_tax_rate(tax) for tax in company_taxes)
                if is_apparel_hsn and rate:
                    if tmpl.list_price <= GST_LOW_SLAB_LIMIT and rate > 5.01:
                        warning = _(
                            "Apparel GST advisory: price is up to Rs. %.0f (expected 5%% slab for readymade garments/footwear), "
                            "but %.2g%% tax is selected. Confirm with your CA.",
                            GST_LOW_SLAB_LIMIT,
                            rate,
                        )
                    elif tmpl.list_price > GST_LOW_SLAB_LIMIT and rate < 17.99:
                        warning = _(
                            "Apparel GST advisory: price exceeds Rs. %.0f per piece (expected 18%% slab from Sep 2025 GST rules), "
                            "but %.2g%% tax is selected. Confirm with your CA.",
                            GST_LOW_SLAB_LIMIT,
                            rate,
                        )
            tmpl.x_gst_slab_warning = warning

