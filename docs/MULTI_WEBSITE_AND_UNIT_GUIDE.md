# 🌐 Multi-Website & New Business Unit Guide (Paths, Domains, Custom Modules & Website Builder)

> **When should you create a New Website (New Business Unit)?**
> Check your live **Scaling Phase Tracker** (`/analytics/roadmap` or **Analytics → Executive Overview → Scaling Phase Tracker (1→5)**):
> * **Phases 1–4 (Same Brand — Apparel Ladies, Men, Kids):** Keep **1 Website** (`yourbrand.in`) and create **URL paths** (`/ladies`, `/men`, `/kids`, `/stores`) so all Google SEO strength stays on one domain.
> * **Phase 4 Gate Cleared → Phase 5 (New Vertical / Franchise / B2B Unit):** When your Progress Tracker reaches **Phase 5** (or you launch a distinct brand like Footwear/Gadgets `gadgetbrand.in` or B2B `partners.yourbrand.in`), create a **New Website** inside this same Odoo database (`zoeemasterdb`).

---

## 1. Create a New Website / Isolated Store

There are two ways depending on whether you want a **dedicated addon codebase (`addons/custom_store_<slug>/`)** or just a **UI-only Builder website**:

### Recommended (With Separate Addon Codebase — One Command Only)
You do **not** need to create the website manually in the Odoo UI first. As long as the target Company already exists in **Settings → Users & Companies → Companies**, just run:
```powershell
.\new_store.bat <slug> "<Website Name>" --company "<Company Name>" --domain "<Domain>" --install
```
- **If the website does not exist yet:** `--install` creates the `website` record in Odoo automatically, sets `x_store_code`, attaches isolated `ir.asset` SCSS/JS, and seeds a Builder-editable starter homepage & footer.
- **If you already created the website in the UI first:** running `.\new_store.bat` with the matching website name links to the existing `website` record without creating a duplicate.

### Alternative (UI-Only Without a Custom Addon Folder)
If you only want a quick Builder-only site without its own `addons/` folder:
1. Log in as Administrator and go to **Website → Configuration → Settings**.
2. Click **+ New Website** (or go to **Website → Configuration → Websites → New**).
3. Fill in **Website Name**, **Website Domain**, and **Company**, then pick a starter theme.

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

### Option A: Create a Dedicated Store Addon Automatically (`new_store.bat`)
Use [`new_store.bat`](../new_store.bat) ([`scripts/new_store.py`](../scripts/new_store.py)) to scaffold an isolated, Website-Builder-compatible module under `addons/custom_store_<slug>/` (scoped via `website.x_store_code` and `ir.asset` `website_id`, so websites never overwrite each other):

```powershell
# Example: FAIRTAG & ZOIRA LAWNS under their branches
.\new_store.bat fairtag "FAIRTAG" --company "FAIRTAG" --domain "http://fairtag.localhost:8069" --install
.\new_store.bat zoira "ZOIRA LAWNS" --company "ZOIRA LAWNS" --domain "http://zoira.localhost:8069" --install

# Start Odoo again after --install finishes
.\.venv\Scripts\python.exe .\odoo\odoo-bin -c .\data\odoo.runtime.conf
```

Each generated `addons/custom_store_<slug>/` folder includes its own `views/` (`homepage.xml`, `footer.xml`, `header.xml`, `shop_templates.xml`, `product_templates.xml`, `cart_templates.xml`, `checkout_templates.xml`), `static/src/scss/` (`primary_variables.scss`, `<slug>.scss`), and `static/src/js/<slug>.js`.

### Option B: Syncing Visual Website Builder Edits <-> Addon Code (`sync_store.bat`)

1. Design or edit pages visually using Odoo's drag-and-drop **Edit (Website Builder)** on any store and click **Save**.
2. Pull the Builder-edited `homepage`, `footer`, and custom `website.page` records from PostgreSQL directly into `addons/custom_store_<slug>/views/`:
   ```powershell
   .\sync_store.bat pull custom_store
   .\sync_store.bat pull fairtag
   ```
3. Or push XML edits made in VS Code (`homepage.xml` / `footer.xml`) back into that store's Builder views in DB:
   ```powershell
   .\sync_store.bat push fairtag
   ```
4. Restart Odoo after upgrading/pushing:
   ```powershell
   .\.venv\Scripts\python.exe .\odoo\odoo-bin -c .\data\odoo.runtime.conf
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

