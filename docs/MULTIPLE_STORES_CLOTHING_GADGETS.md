# Multiple Online Stores (Clothing vs. Gadgets: When & How)

Odoo `20.0` (`website` + `website_sale`) natively supports **Multi-Website** and **Multi-Company** inside a single Odoo instance and database — you do **not** need a second server or separate codebase to run two distinct storefronts.

---

## 1. When Should You Launch a Second Store for Gadgets? (`SCALING_ROADMAP.md`)

Per [`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md) (Sections 9–10):

* **Do NOT launch Gadgets in Phases 1–4:** Electronics/gadgets have thinner margins (5–15%), different buyers, warranty/DOA returns, IMEI/serial tracking, and dilute a fashion brand.
* **Recommended expansion order:** Fabrics (`Phase 2–5`) → Footwear (`Phase 4–5`) → Jewellery/Accessories (`Phase 4–5`) → **Gadgets in Phase 5** (after passing Gate 4: ₹1.5 Cr+/month revenue for 3 months).
* **Brand separation rule:** Keep Clothing (`yourbrand.in`) and Gadgets (`gadgetbrand.in` / `yourbrand-gadgets.in`) as **two separate websites** (different brand names, domains, themes, catalogs, and ideally a separate Odoo **Company** such as `YourBrand Tech LLP` for clean GST & P&L separation).

---

## 2. How to Set Up Two Stores on One Odoo Backend

1. **Create Website #2 in Odoo:**
   * Go to **Website → Configuration → Settings** and click **`+ New Website`** (`action_website_create_new`).
   * Fill in **Name** (e.g. `Gadgets Store`), **Domain** (e.g. `https://gadgetbrand.in` in production), **Company** (same company or your separate Gadgets company when multi-company is enabled), and configure its theme.
2. **Scope Products, Categories & Store Settings per Website (`website_id`):**
   * Once 2+ websites exist (`website.group_multi_website` activates automatically), set **Website** (`website_id`) so Clothing & Gadgets never mix:
     * **Products** (`eCommerce` tab → `website_id`) — show apparel only on Website 1 and gadgets only on Website 2.
     * **eCommerce Categories** (**eCommerce → Configuration → eCommerce Categories** → `website_id`) — assign `Ladies / Men / Kids` ([`public_category_data.xml`](../addons/custom_store/data/public_category_data.xml)) to Clothing Website 1 and create separate Gadgets categories on Website 2.
     * **Pricelists, Promotions/Loyalty, Shipping Methods & Payment Providers** (`website_id` field on each) — use distinct Razorpay keys, shipping carriers, or promo codes per store if needed.
     * **Customer Accounts (`shared_user_account`):** Under **Website → Configuration → Settings**, choose whether customers share one account across both websites or keep separate accounts per store.
3. **Separate Storefront Themes & Copy in `addons/custom_store/` (Important Code Note):**
   * Currently, `addons/custom_store/` inherits base views (`website.homepage`, `website.layout`, `website_sale.products`, `website_sale.product`) globally with apparel copy (*"View Apparel Size Guide"*, *"QC Verified Garment"*, *"7-Day Easy Size Exchange"*).
   * When launching Website #2 in code, either:
     * Scope apparel-only blocks/copy in `addons/custom_store/` to Website #1 (e.g. `t-if="website.id == ..."` / `website.name`), **or**
     * Assign store-specific views (`ir.ui.view.website_id`) or add a dedicated module such as `addons/custom_store_gadgets/`, while skipping `x_fabric` / size-guide PDP sections on gadget products (and enabling **Lots & Serial Numbers** + **`repair`** for IMEI/warranty tracking instead).
4. **Domain Routing & SSL (`deploy/nginx.conf`):**
   * [`deploy/nginx.conf`](../deploy/nginx.conf) already forwards `Host $http_host` and `X-Forwarded-Host $http_host` (`server_name _;`). When going live with two domains, point both domains' DNS to your VPS, configure SSL certificates for both domains in Nginx, and set each URL in **Website → Configuration → Websites** (`domain` field) so Odoo automatically serves Store #1 or Store #2 based on the visitor's domain.

