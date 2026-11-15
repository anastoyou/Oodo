# Where to Edit the Website & eCommerce Site

> Refer to [`help.md`](../help.md) for active local (`http://localhost:8069`) and tunnel URLs.

---

## Option A: Visual Edits in the Live Browser (Saved in DB / Filestore)

Log in at `/web/login`:

* **Website pages (`/`, `/size-guide`, `/shipping-policy`, `/return-policy`, `/support`, `/blog`):**
  * Open the page and click **Edit** (top-right) to use Odoo's drag-and-drop **Website Builder** and **Theme** options.
  * Or open `/odoo` → **Website** app to manage pages, menus, redirects, and site configuration.
* **eCommerce store (`/shop`, product pages, cart, checkout):**
  * Open `/shop`, `/shop/cart`, or any product page and click **Edit** to configure layout, shop cards, filters, and Theme settings.
  * Open `/odoo` → **eCommerce** app to manage products, pricing, eCommerce categories, Razorpay/COD payment providers, shipping methods, and loyalty/coupons.

---

## Option B: Code Edits in `addons/custom_store/` (Git-Tracked & Upgrade-Safe)

All storefront & eCommerce code lives in [`addons/custom_store/`](../addons/custom_store/README.md) (outside `odoo/`):

| Area | File in `addons/custom_store/` |
| :--- | :--- |
| Brand palette & SCSS variables | [`static/src/scss/primary_variables.scss`](../addons/custom_store/static/src/scss/primary_variables.scss) |
| Storefront, Cart, Checkout & Portal styles/JS | [`static/src/scss/custom_store.scss`](../addons/custom_store/static/src/scss/custom_store.scss), [`static/src/js/custom_store.js`](../addons/custom_store/static/src/js/custom_store.js) |
| Header & announcement bar | [`views/header.xml`](../addons/custom_store/views/header.xml) |
| Homepage hero, sections & trust cards | [`views/homepage.xml`](../addons/custom_store/views/homepage.xml) |
| Footer navigation & links | [`views/footer.xml`](../addons/custom_store/views/footer.xml) |
| eCommerce `/shop` banner & layout | [`views/shop_templates.xml`](../addons/custom_store/views/shop_templates.xml) |
| Product detail page (`/shop/<product>`) | [`views/product_templates.xml`](../addons/custom_store/views/product_templates.xml) |
| Shopping cart (`/shop/cart`) | [`views/cart_templates.xml`](../addons/custom_store/views/cart_templates.xml) |
| Checkout & confirmation (`/shop/checkout`) | [`views/checkout_templates.xml`](../addons/custom_store/views/checkout_templates.xml) |
| Public `/shop` categories | [`data/public_category_data.xml`](../addons/custom_store/data/public_category_data.xml) |
| Customer Portal & Tickets (`/my`, `/my/tickets`) | [`views/portal_templates.xml`](../addons/custom_store/views/portal_templates.xml), [`views/portal_support_templates.xml`](../addons/custom_store/views/portal_support_templates.xml), [`data/portal_entry_data.xml`](../addons/custom_store/data/portal_entry_data.xml) |
| Policy & support pages (`/size-guide`, `/shipping-policy`, `/return-policy`, `/support`) | `addons/custom_store/views/pages/*.xml` (`size_guide.xml`, `shipping_policy.xml`, `return_policy.xml`, `support.xml`) |
| Web controllers | [`controllers/main.py`](../addons/custom_store/controllers/main.py), [`controllers/portal.py`](../addons/custom_store/controllers/portal.py) |

After editing files in `addons/custom_store/`, reload them into PostgreSQL:

```bat
.\upgrade.bat --skip-pull
.\start.bat
```

