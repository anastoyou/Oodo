# `custom_store` — Version-Controlled Website, eCommerce, Checkout, Portal & Support Addon

This module lives in `e:\Code\Oodo\addons\custom_store` (tracked in Git, completely outside the gitignored `odoo/` directory) and builds on top of `custom_erp`.
Core `website`, `website_sale`, `website_sale_loyalty`, `portal`, `auth_signup`, and `theme_default` stay untouched inside `odoo/addons/` so upstream Odoo `20.0` updates (`upgrade.bat`) never conflict with your storefront or customer portal customizations.

## Where to Customize

| Area | File in `addons/custom_store/` |
| :--- | :--- |
| Brand colors & palette (`#f06030`, `#0c151b`, etc.) | `static/src/scss/primary_variables.scss` |
| Storefront, Cart, Checkout, Portal SCSS | `static/src/scss/custom_store.scss` |
| Frontend JS (`Interaction`) | `static/src/js/custom_store.js` |
| Top announcement bar & Header navbar | `views/header.xml` |
| Homepage sections, hero, collections, trust cards | `views/homepage.xml` |
| Footer navigation & Customer Care links | `views/footer.xml` |
| Storefront `/shop` public categories | `data/public_category_data.xml` |
| `/shop` catalog banner & card styles | `views/shop_templates.xml` |
| Product detail page (`/shop/<product>`) specs & badges | `views/product_templates.xml` |
| Shopping cart (`/shop/cart`) notice & styling | `views/cart_templates.xml` |
| Checkout flow, payment tips & order confirmation | `views/checkout_templates.xml` |
| Customer login, signup, `/my` portal, order sidebar | `views/portal_templates.xml` |
| Portal Helpdesk entry & `/my/tickets` templates | `data/portal_entry_data.xml`, `views/portal_support_templates.xml` |
| Policy & Support pages (`/size-guide`, `/shipping-policy`, `/return-policy`, `/support`) | `views/pages/*.xml` |
| Storefront & Support Portal controllers | `controllers/main.py`, `controllers/portal.py` |
