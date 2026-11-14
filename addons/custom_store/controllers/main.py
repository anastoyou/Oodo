from odoo.addons.website_sale.controllers.main import WebsiteSale


class CustomStoreWebsiteSale(WebsiteSale):
    """Extension controller for custom storefront and eCommerce behavior."""

    def _prepare_product_values(self, product, **kwargs):
        """Extend QWeb context available on product detail pages (/shop/<product>)."""
        values = super()._prepare_product_values(product, **kwargs)
        # Add custom template context keys here without modifying odoo/addons/website_sale.
        return values

