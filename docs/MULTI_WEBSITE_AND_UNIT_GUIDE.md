# 🌐 Multi-Website & New Business Unit Guide (Paths, Domains, Custom Modules & Website Builder)

> **When should you create a New Website (New Business Unit)?**
> Check your live **Scaling Phase Tracker** (`/analytics/roadmap` or **Analytics → Executive Overview → Scaling Phase Tracker (1→5)**):
> * **Phases 1–4 (Same Brand — Apparel Ladies, Men, Kids):** Keep **1 Website** (`yourbrand.in`) and create **URL paths** (`/ladies`, `/men`, `/kids`, `/stores`) so all Google SEO strength stays on one domain.
> * **Phase 4 Gate Cleared → Phase 5 (New Vertical / Franchise / B2B Unit):** When your Progress Tracker reaches **Phase 5** (or you launch a distinct brand like Footwear/Gadgets `gadgetbrand.in` or B2B `partners.yourbrand.in`), create a **New Website** inside this same Odoo database (`zoeemasterdb`).

---

## 1. Create the New Website (New Unit) in Odoo

1. Log in as Administrator and go to **Website → Configuration → Settings**.
2. Click **+ New Website** (or go to **Website → Configuration → Websites → New**).
3. Fill in the unit details:
   * **Website Name:** e.g. `YourBrand Gadgets` or `YourBrand Partners`
   * **Website Domain:** e.g. `http://unit2.localhost:8069` (local dev) or `https://gadgetbrand.in` (production)
   * **Company:** Select your main company (shared inventory/accounting) or a separate Phase 5 subsidiary company (e.g., `YourBrand Tech LLP`).
4. Pick a starter theme (`theme_default`) when the Website Builder configurator opens.

---

## 2. How Domains Work (Local Windows Dev vs Production VPS)

Odoo matches every incoming HTTP request's `Host` header against the **Domain** field on each `website` record:

### A. Local Windows Development (Testing 2 Websites on `localhost:8069`)
1. Chromium/Edge/Firefox on Windows 10/11 resolve `*.localhost` to `127.0.0.1` automatically:
   * **Site 1 (Main Apparel):** Leave **Domain** empty (fallback) or set `http://localhost:8069`
   * **Site 2 (New Unit):** Set **Domain** to `http://unit2.localhost:8069`
   * If you want custom domains locally (e.g., `unit2.local`), add `127.0.0.1 unit2.local` as Administrator to `C:\Windows\System32\drivers\etc\hosts`.
2. Ensure `odoo.runtime.conf` / `odoo.conf` keeps `dbfilter = ^zoeemasterdb$` (or `--db-filter ^zoeemasterdb$`) so visiting `http://unit2.localhost:8069` automatically loads `zoeemasterdb` and renders Site 2 instead of showing the database selector screen.

### B. Production Cloud VPS (Docker + Nginx)
1. Point your new domain's DNS **A Record** (`gadgetbrand.in`, `www.gadgetbrand.in`, or `partners.yourbrand.in`) to your VPS IP address.
2. Add the new domain to Nginx (`deploy/nginx/`) forwarding `Host` and `X-Forwarded-Host` with `proxy_mode = True` in `odoo.conf`:
   ```nginx
   server {
       listen 80;
       server_name gadgetbrand.in www.gadgetbrand.in;
       location / {
           proxy_pass http://odoo:8069;
           proxy_set_header Host $http_host;
           proxy_set_header X-Forwarded-Host $http_host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```
3. Run Certbot/Let's Encrypt for HTTPS on the new domain and set **Website Domain** in Odoo to `https://gadgetbrand.in`.

---

## 3. How URL Paths & Visibility Work Across Websites

Inside the same Odoo database, records can either be **shared across all websites** or **locked to one Website Unit**:

| Record Type | Where to Scope | Rule |
| :--- | :--- | :--- |
| **Pages (`/size-guide`, `/warranty`, `/b2b`)** | **Website → Site → Pages** (`website.page`) | Set `Website` = Site 2. Both Site 1 and Site 2 can even have their own `/about` or `/terms` URL independently when scoped by `website_id`. |
| **Navigation Menus** | **Website → Site → Menu Editor** (`website.menu`) | Each website automatically has its own isolated top/footer menu tree tied to `website_id`. |
| **Products & Shop Categories** | Product Form → **Sales** tab → **Website** (`website_id`) & **eCommerce Categories** (`website_id`) | Leave blank to sell on all websites, or set **Website = YourBrand Gadgets** so gadgets only show on Site 2's `/shop`. |
| **Homepage (`/`)** | Automatically scoped via `website.homepage` Copy-on-Write (`website_id`) | Editing `/` on Site 2 never alters Site 1's homepage (`addons/custom_store/views/homepage.xml`). |

---

## 4. Moving Your New Website Into a Custom Module (Version Control)

Do **not** edit files inside `odoo/`. Keep every business unit's code inside `addons/` just like [`addons/custom_store/`](../addons/custom_store/README.md).

### Option A: Create a Dedicated Unit Module (Recommended for Separate Brand / Unit)
Create `addons/custom_unit2/`:
```text
addons/custom_unit2/
├── __init__.py
├── __manifest__.py
├── data/
│   └── website_unit2_data.xml
├── static/src/scss/
│   └── unit2_styles.scss
└── views/
    └── unit2_pages.xml
```

**`addons/custom_unit2/__manifest__.py`:**
```python
{
    "name": "Custom Unit 2 Website",
    "version": "20.0.1.0.0",
    "category": "Website/eCommerce",
    "depends": ["website", "website_sale", "theme_default"],
    "data": [
        "data/website_unit2_data.xml",
        "views/unit2_pages.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "custom_unit2/static/src/scss/unit2_styles.scss",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}
```

> [!IMPORTANT]
> **Asset Scoping Warning (`web.assets_frontend`):**
> `web.assets_frontend` is compiled globally for the database, whereas custom SCSS variables (`user_values.scss`) set in Website Builder are stored per website. Do **not** override global `$o-brand-primary` inside a second addon's `web._assets_primary_variables`, or it will overwrite Site 1's colors! Instead, customize colors per site in **Website → Edit → Theme**, or wrap CSS rules inside `[data-website-id="2"] { ... }`.

### Option B: Exporting Pages Built with Odoo Website Builder Into Your Addon

1. Design your new page visually using Odoo's drag-and-drop **Edit (Website Builder)** on Site 2 and click **Save**.
2. Inspect/export the saved QWeb view XML for that `website_id` from `odoo-bin shell`:
   ```python
   # Run via: .\.venv\Scripts\python.exe .\odoo\odoo-bin shell -c .\data\odoo.runtime.conf -d zoeemasterdb --no-http
   for page in env["website.page"].search([("website_id", "=", 2)]):
       print("=== URL:", page.url, "| KEY:", page.view_id.key, "===")
       print(page.view_id.arch_db)
   ```
3. Paste the exported `<t t-call="website.layout">...</t>` XML into `addons/custom_unit2/views/unit2_pages.xml` and install/upgrade with:
   ```powershell
   .\.venv\Scripts\python.exe .\scripts\odoo_ctl.py upgrade --skip-pull --install --modules custom_unit2
   ```

---

## 5. Crucial Rules So the Odoo Website Builder Always Works

When moving Website pages into a custom XML module, follow these 5 rules (otherwise drag-and-drop editing, snippets, or future upgrades break):

1. **Always include `<div id="wrap" class="oe_structure">`:**
   Every page template inside `<t t-call="website.layout">` must wrap editable content in `<div id="wrap" class="oe_structure">` (or `oe_structure oe_empty`), matching [`size_guide.xml`](../addons/custom_store/views/pages/size_guide.xml). Without `oe_structure`, the **Website Builder** sidebar disables block drop zones.
2. **Use `<section class="s_..." data-snippet="s_...">` for blocks:**
   Keep standard Odoo snippet classes (`s_cover`, `s_text_image`, `s_three_columns`, `o_cc`, `o_colored_level`, `s_allow_columns`) so the Builder recognizes every block for padding, background color, and duplication tools.
3. **Never hardcode `website.id` numbers in `website_id` XML IDs without `<data noupdate="1">`:**
   Look up or create the `website` record cleanly via XML ID or `search` / `<record id="website_unit2" model="website">` inside `<data noupdate="1">`, and reference `ref="website_unit2"` on `website.page` and `website.menu`.
4. **Choose `noupdate="1"` vs `noupdate="0"` intentionally:**
   * **`<data noupdate="1">` (Builder-First):** Module creates initial Seed Pages/Menus on install; afterwards, non-technical staff can freely edit text/images in **Website Builder** without losing changes on `upgrade.bat`.
   * **`<data noupdate="0">` (Git-First — like `custom_store`):** Module overwrites the base template cleanly on every `upgrade.bat`. Note: when a user edits a page in Website Builder on a specific site, Odoo triggers **Copy-on-Write (CoW)** and forks a website-specific `ir.ui.view` record in the DB so Site Builder stays functional!
5. **Never bind `<xpath position="replace">` to break core IDs (`top_menu`, `footer`, `wrapwrap`, `oe_main_menu_navbar`):**
   Keep structural IDs and classes intact (as done in [`header.xml`](../addons/custom_store/views/header.xml) and [`footer.xml`](../addons/custom_store/views/footer.xml)), so Header/Footer style switchers inside Website Builder continue to work.

