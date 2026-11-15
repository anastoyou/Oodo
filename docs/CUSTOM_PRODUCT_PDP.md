# Creating a Custom PDP (Product Detail Page) for Each Product

In Odoo `20.0` (`website_sale`), every product page (`/shop/<product>`) is rendered by `WebsiteSale.product()` ([`website_sale/controllers/main.py`](../odoo/addons/website_sale/controllers/main.py)) using the template `website_sale.product` ([`product_page_templates.xml`](../odoo/addons/website_sale/templates/product_page_templates.xml)).

Depending on how unique each SKU page needs to be, choose from these **4 approaches**:

---

## Method 1: Unique Drag-and-Drop Content Per Product (No Code)

Odoo `20.0` stores **4 per-product HTML fields** directly on each `product.template` record, so editing one product does **not** affect other products:

| Region on `/shop/<product>` | Field on `product.template` | Where to edit |
| :--- | :--- | :--- |
| Short promo / rich copy below rating | `description_ecommerce` | Inline on PDP (**Edit**) or Backend → **Products → eCommerce tab → Long Description** |
| Drop zone right **above price** | `dropzone_above_price` (`website_sale.container_dropzone_above_price`) | Open that product `/shop/<product>` → click **Edit** → drop blocks there |
| Drop zone **above specifications** (below Add to Cart) | `dropzone_above_specification` (`website_sale.container_dropzone_above_specification`) | Open that product `/shop/<product>` → click **Edit** → drop blocks there |
| **Full-width lower PDP story / lookbook** (`#product_full_description`) | `website_description` | Open that product `/shop/<product>` → click **Edit** → drag full Website Builder sections (banners, columns, lookbooks, FAQs) into the bottom canvas |

> **Watch out for global zones:** When editing a product in Website Builder, `#oe_structure_website_sale_product_1`, `#oe_structure_website_sale_product_2`, and `website_sale.container_dropzone_below_product_details` state **"on all products"** — blocks dropped in those zones appear on *every* product, whereas the 4 fields above stay **unique per product**.

---

## Method 2: Structured Per-Product Specs (Consistent Design, Different Data Per SKU)

Already implemented in this project:
1. [`addons/custom_erp/models/product_template.py`](../addons/custom_erp/models/product_template.py) defines per-product fields (`x_fabric`, `x_fit_type`, `x_wash_care`, `x_dispatch_days`).
2. [`addons/custom_store/views/product_templates.xml`](../addons/custom_store/views/product_templates.xml) inherits `website_sale.product` and renders the `.o_custom_store_specs` card whenever any of those fields are populated on that product (`t-if="product.x_fabric or ..."`).

To add new per-product PDP sections (for example model stats, blouse/dupatta details, video URL, or care icons):
1. Add the field(s) to `ProductTemplate` in `addons/custom_erp/models/product_template.py` and expose them in `addons/custom_erp/views/product_views.xml`.
2. Add the QWeb block in `addons/custom_store/views/product_templates.xml` wrapped in `t-if="product.<field>"` so it renders only on products where you fill that data.
3. Run `.\upgrade.bat --skip-pull` and `.\start.bat`.

---

## Method 3: Per-Product or Per-Category Layout Variants in QWeb

If certain products or categories (e.g., *Sarees*, *Unstitched Fabrics*, *Flagship Festive Edit*) need extra sections or a different visual layout:

1. Add a `Selection` field on `product.template` in `addons/custom_erp/models/product_template.py`:
   ```python
   x_pdp_layout = fields.Selection(
       [("standard", "Standard Apparel"), ("editorial", "Editorial Showcase"), ("fabric", "Unstitched Fabric")],
       string="PDP Layout",
       default="standard",
   )
   ```
   *(Or check `product.public_categ_ids` directly without adding a field.)*
2. In `addons/custom_store/views/product_templates.xml`, conditionally show or swap sections with `t-if="product.x_pdp_layout == 'editorial'"`.

---

## Method 4: 100% Bespoke QWeb Template Per Product (Controller Override)

For flagship SKUs needing a completely custom `/shop/<product>` page template while keeping variants, pricing, and Add-to-Cart intact:

1. Create a custom QWeb template XML in `addons/custom_store/views/` (registered in `addons/custom_store/__manifest__.py`), such as `custom_store.product_page_bespoke`, or pass extra context from `CustomStoreWebsiteSale` in [`addons/custom_store/controllers/main.py`](../addons/custom_store/controllers/main.py).
2. Store a template key on `product.template` (e.g., `x_custom_pdp_xmlid` in `custom_erp`), then override `product()` in `CustomStoreWebsiteSale` (`addons/custom_store/controllers/main.py`, inheriting `WebsiteSale`) to render that product's template with `self._prepare_product_values(...)` instead of `"website_sale.product"` when `x_custom_pdp_xmlid` is set.
3. *(Simpler no-code alternative for campaign launches)*: keep `/shop/<product>` standard and create a dedicated Website landing page (`/my-launch`) using Website Builder + Odoo's **Add to Cart (`s_add_to_cart`)** snippet linked to that product.

