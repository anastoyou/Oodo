# End-to-End ERP Setup Flow (`1 → 67`): Base Engine to Production & Phase 1–5 Scaling

> **Target Stack:** Odoo 20.0 Community Edition (`odoo/`) + Custom Addons (`addons/custom_erp`, `addons/custom_store`) + Standalone PostgreSQL 16 (`shared-postgres`) + Linux Docker Production (`deploy/`)
> **Company:** `ZOEE GLOBAL PRIVATE LIMITED` (India / INR / Surat Base)
> **Brands:** `FAIRTAG`, `ZOIRA`, `GADGETS`
> **Database:** `zoeemasterdb`
> **Companion Strategy:** [`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md) (Phase 1 → Phase 5 Business & Technical Gates) & [`ROADMAP_MODULE_STATUS.md`](./ROADMAP_MODULE_STATUS.md)

---

## How to Use This Document

This guide is the **complete 1-to-End Engine Blueprint ("base level to end level")** for setting up the entire ERP from a blank machine all the way to multi-brand production deployment.

Every step from **1 to 67** is documented in **strict setup dependency order** and tagged with two labels:
- **When to activate (Roadmap Gate):** `Phase 1 (Day-1)` vs `Phase 2` / `Phase 3` / `Phase 4` / `Phase 5` per [`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md).
  - **Rule #1 from the Roadmap:** Build the clean **Phase 1 Engine first**. Do **not** activate Retail POS (Phase 3), Multi-Company (Phase 5), or the `GADGETS` Storefront (Phase 5) on Day 1—keep the Day-1 schema/naming ready for them, and turn them on only when the revenue/volume Gate triggers.
- **Layer:**
  - `Infra / DevOps` — Docker, PostgreSQL, `.env`, `odoo.conf`, Nginx, scripts
  - `Odoo 20.0 Built-In` — Native Odoo 20.0 Community modules & settings
  - `Custom Addon (Included)` — Already implemented in `addons/custom_erp/` or `addons/custom_store/`
  - `OCA / External / Phase Extension` — Community OCA modules or external APIs added at Phase 2–5

> **Doc Alignment Note:** Earlier strategy notes in [`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md) referenced an initial `Odoo 18` / `start.bat` / `config/odoo.conf` layout. The live repository runs **Odoo 20.0 Community** with root [`odoo.conf`](../odoo.conf), standalone [`docker-compose.yml`](../docker-compose.yml) (`shared-postgres`), manual `odoo-bin` startup, and [`scripts/odoo_ctl.py`](../scripts/odoo_ctl.py) wrappers (`save_db.bat`, `load_db.bat`, `remove_db.bat`, `upgrade.bat`). Both are reconciled below.

---

## 1-to-End Engine Architecture Map

```
[Stage A: Infrastructure & DB]       Steps 1–3   : Odoo 20.0 + .venv + shared-postgres + zoeemasterdb
        │
[Stage B: Legal, Finance & Org]      Steps 4–18  : ZOEE GLOBAL PRIVATE LIMITED + INR + GST (l10n_in) + COA + Banks + Brands (FAIRTAG/ZOIRA/GADGETS) + Users/Groups/HR
        │
[Stage C: Master Data & Catalog]     Steps 19–28 : Contacts/Customers/Vendors + Categories + Attributes + Brands + SKUs/Barcodes + UoM + Pricelists
        │
[Stage D: Supply Chain & Stock]      Steps 29–35 : Warehouses + Locations + Operations + Reordering + Purchasing + Vendor Pricelists + PO Approvals
        │
[Stage E: Omnichannel Sales & Web]   Steps 36–49 : Sales + Teams + Quote Templates + CRM + Websites + Multi-Website + Payments + Shipping + POS (Phase 3)
        │
[Stage F: Finance Close & Ops]       Steps 50–60 : Invoices + Expenses + Analytics + Financial Reports + Email + Automations + Approvals + Docs + Helpdesk + Returns/RTO + Dashboards
        │
[Stage G: Governance & Go-Live]      Steps 61–67 : ir.access Security + Backups + Data Migration + Custom Addons + Integration Tests + UAT + Prod Deployment
```

---

## Stage A — Foundation Infrastructure (Steps 1–3)

### 1. Odoo Installation & Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Infra / DevOps`
- **What is installed:** Odoo 20.0 Community source in [`odoo/`](../odoo/) paired with Python 3.12 virtual environment (`.venv/`), root [`odoo.conf`](../odoo.conf), and environment file [`.env`](../.env) (templated from [`.env.example`](../.env.example)).
- **Key settings in [`odoo.conf`](../odoo.conf):**
  - `http_interface = 0.0.0.0`, `http_port = 8069`
  - `addons_path = E:\Code\Oodo\odoo\addons,E:\Code\Oodo\addons`
  - `data_dir = E:\Code\Oodo\data` (stores `filestore/<db>/` and `sessions/`)
  - `list_db = True` (local dev only; set `False` in production)
  - `admin_passwd = zoeeadmin` (dev master password; rotate before going live)
  - `db_host = localhost`, `db_port = 5432`, `db_user = odoo`, `db_password = odoo`
- **Verify & Run Server Manually:**
  ```powershell
  .\.venv\Scripts\python.exe .\odoo\odoo-bin -c .\odoo.conf
  ```
- **Details:** [`ARCHITECTURE_AND_CUSTOM_ERP.md`](./ARCHITECTURE_AND_CUSTOM_ERP.md), [`MODULES_AND_DB_PORTABILITY.md`](./MODULES_AND_DB_PORTABILITY.md).

### 2. PostgreSQL Database Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Infra / DevOps`
- **Shared Database Architecture:** Defined in [`docker-compose.yml`](../docker-compose.yml) as a standalone, project-neutral PostgreSQL 16 container so multiple local projects can share the same database engine:
  - Container / Service: `shared-postgres` (`postgres:16-alpine`)
  - Persistent Volume: `shared-postgres-data`
  - Network: `shared-db-network` (aliases: `shared-postgres`, `postgres`, `shared-db`)
  - Port: `5432:5432`
  - Superuser: `postgres` / `postgres` (overridable via `.env`)
- **Critical Odoo Rule (`db_user != postgres`):** Odoo's CLI explicitly aborts if `db_user` is `postgres` (`odoo/odoo/cli/server.py`). Keep container superuser `postgres` neutral, and create dedicated Odoo role `odoo` (`SUPERUSER` / `CREATEDB`) matching `.env` (`DB_USER=odoo`, `DB_PASSWORD=odoo`).
- **Start PostgreSQL:**
  ```powershell
  docker compose up -d
  ```
- **Note:** [`load_db.bat`](../load_db.bat) automatically provisions `DB_USER` on a fresh `shared-postgres` container before restoring a dump.

### 3. Database Creation
- **When:** `Phase 1 (Day-1)` | **Layer:** `Infra / DevOps` / `Odoo 20.0 Built-In`
- **Database Name Standard:** `zoeemasterdb` (`ODOO_DB=zoeemasterdb` in `.env` and `deploy/backup_db.sh`).
  - **Never** leave `db_name = localhost` or browse without selecting `zoeemasterdb`—Odoo interprets unmapped hosts as DB names when `dbfilter` is unset. Keep `ODOO_DB=zoeemasterdb` consistent across `.env` and commands.
- **Two clean ways to create/initialize `zoeemasterdb`:**
  1. **Restore an existing golden snapshot:** Run [`load_db.bat`](../load_db.bat) and pick a backup zip from `backups/` (targets `zoeemasterdb` by default).
  2. **Initialize a brand-new database with base + custom modules:**
     ```powershell
     .\.venv\Scripts\python.exe .\odoo\odoo-bin -c .\odoo.conf -d zoeemasterdb -i custom_erp,custom_store --without-demo=all --stop-after-init
     ```
     Or create via `http://localhost:8069/web/database/manager` (`Master Password: zoeeadmin`, Database Name: `zoeemasterdb`, Country: `India`, Language: `English (US)` / `English (IN)`) and then install `custom_erp` and `custom_store`.
- **Reset / Clean Removal (Dev Testing):** Run [`remove_db.bat`](../remove_db.bat) (`remove_db.bat zoeemasterdb`) to drop the DB, remove `data/filestore/zoeemasterdb`, and prune stale sessions.

---

## Stage B — Company, Indian Localization, Accounting Foundation & Org Structure (Steps 4–18)

### 4. Company Setup – `ZOEE GLOBAL PRIVATE LIMITED`
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Settings → Users & Companies → Companies`
- **Configure:**
  - **Company Name:** `ZOEE GLOBAL PRIVATE LIMITED`
  - **Primary Domain Rule:** Legal operating entity for `FAIRTAG` and `ZOIRA` (and initial `GADGETS` accounting until Phase 5 determines whether to stay consolidated or split legal entities).
  - Ensure your Admin user has `ZOEE GLOBAL PRIVATE LIMITED` set as active Company and check **Show Full Accounting Features** on Admin user (`Settings → Users & Companies → Users → Access Rights`) so full Accounting menus (`Chart of Accounts`, `Journal Entries`, `Journals`, `Partner Ledger`) become visible in Odoo 20.0 Community.

### 5. Company Information & Logo
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Settings → Companies → Update Info`
- **Configure:**
  - High-res corporate logo (`ZOEE GLOBAL PRIVATE LIMITED` header mark for invoices/POs/quotes; brand-specific store logos go per-Website in Step 42).
  - Registered Address, City (`Surat`), State (`Gujarat (GJ)`), PIN, Country (`India`).
  - Phone, official support/billing email, Website URL, Corporate Identity Number (CIN) in Company Registry, and **GSTIN** (`Tax ID`).
  - Document Footer (`Registered Office`, bank payment summary for B2B invoices) via `Settings → General Settings → Business Documents → Configure Document Layout`.

### 6. Currency Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Accounting → Configuration → Currencies` & `Settings → Accounting → Currencies`
- **Configure:**
  - **Main Company Currency:** `INR` (`₹`, symbol before amount, 2 decimal precision).
  - **Multi-Currency (Phase 4–5 optional):** Activate `USD` / `AED` / `GBP` only if exporting internationally or importing Gadgets components directly, and configure automatic FX rate sync (`ECB` / `RBI` feed or manual weekly rate). Keep pure `INR` in Phase 1–3.

### 7. Country & Localization Settings
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` + `Custom Addon (Included)`
- **Modules Installed (`custom_erp` dependencies):** `l10n_in`, `l10n_in_sale`, `l10n_in_stock` (plus `l10n_in_edi` when e-Invoicing threshold applies, and `l10n_in_pos` in Phase 3).
- **Path:** `Accounting → Configuration → Settings → Indian Localization` & `Fiscal Localization`
- **Configure:**
  - **Fiscal Localization Package:** `India` (`l10n_in`).
  - Verify State codes (`Gujarat - 24` for Surat hub) so IGST vs CGST+SGST Fiscal Positions auto-switch based on customer delivery/billing state!
  - Enable **HSN/SAC codes** on all products and set Company GST Registration Type (`Regular` or `Composition`—must be `Regular` for inter-state eCommerce/marketplace selling).
  - Configure **Indian e-Invoice (`l10n_in_edi`) & E-Way Bill** credentials when B2B turnover / single-consignment threshold (`> ₹50,000`) requires IRN/EWB generation.

### 8. Chart of Accounts Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` + `Manual Business Config`
- **Path:** `Accounting → Configuration → Chart of Accounts` (requires **Show Full Accounting Features** enabled)
- **Verify & Add Accounts (`l10n_in` base + 2-Partner & E-Commerce additions per [`PARTNER_ACCOUNTING_AND_SALARIES.md`](./PARTNER_ACCOUNTING_AND_SALARIES.md)):**
  - **Equity / Partner Capital:** `Partner A – Capital Account`, `Partner B – Capital Account`.
  - **Partner Current / Drawings / Loan:** `Partner A – Current / Loan Account`, `Partner B – Current / Loan Account` (track seed injections, drawings, and monthly salaries cleanly).
  - **Income:** `D2C Website Sales`, `Marketplace Sales (Myntra/Ajio/Amazon/Flipkart)`, `Retail POS Sales` (Phase 3), `Shipping Charges Collected`, `B2B Wholesale Sales`.
  - **COGS & Direct Expenses:** `Cost of Goods Sold – Apparel`, `Job-Work / Stitching Charges`, `Packaging & Hang-Tags`, `Shipping & Courier Expense (Forward + RTO)`, `Payment Gateway Charges (Razorpay)`, `Marketplace Commission & Ads`.
  - **Operating Expenses:** `Performance Marketing (Meta/Google)`, `Staff & Partner Remuneration`, `Warehouse / Store Rent & Utilities`, `Returns / Damaged Goods Write-off`.
  - **Clearing / Escrow Accounts:** `Razorpay Clearing Account`, `COD Courier Remittance Receivable (Shiprocket/Delhivery)`, `Marketplace Settlement Clearing`.

### 9. Tax Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` + `Custom Addon (Included)`
- **Path:** `Accounting → Configuration → Taxes` & `Fiscal Positions`
- **Configure:**
  - **Apparel GST Slabs (Verified with CA; built into [`addons/custom_erp/models/product_template.py`](../addons/custom_erp/models/product_template.py)):**
    - `5% GST` (2.5% CGST + 2.5% SGST / 5% IGST) for readymade apparel & footwear priced **up to ₹2,500** per piece (`HSN 61, 62, 63, 5407, 5208, 64`).
    - `18% GST` (9% CGST + 9% SGST / 18% IGST) for apparel **above ₹2,500** per piece (`custom_erp` automatically displays `x_gst_slab_warning` if price vs selected tax rate conflicts!).
  - **Gadgets GST Slabs (Phase 5):** Typically `18% GST` (`HSN 85xx / 84xx`) or `28%` for applicable electronics—confirm HSN per SKU with CA.
  - **Purchase Taxes (Input Tax Credit):** Matching 5%, 12%, 18% Input GST + RCM (Reverse Charge) taxes for GTA/courier/legal services if applicable.
  - **Fiscal Positions:** Verify `l10n_in` auto-maps Intra-State (`CGST + SGST`) vs Inter-State (`IGST`) vs Export/Zero-Rated (`0%`) based on Customer State/Country.
  - **eCommerce Price Display:** Configure **Tax-Included** (`B2C D2C MRP` standard in India) on Website Pricelists while preserving GST tax breakdown on Invoices.

### 10. Fiscal Year Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Accounting → Configuration → Settings → Fiscal Periods`
- **Configure:**
  - **Fiscal Year Last Day:** `31` `March` (Indian Financial Year: **1 April → 31 March**).
  - **Invoicing Switch Threshold / Lock Dates:** After GST GSTR-1 / GSTR-3B monthly filing, set **Tax Lock Date** (`11th`/`20th` of following month) and after annual statutory audit by CA, set **Fiscal Year Lock Date** (`31 March`).

### 11. Bank Account Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Accounting → Configuration → Add a Bank Account` / `Journals`
- **Configure:**
  - Add company Current Bank Account(s) (`ZOEE GLOBAL PRIVATE LIMITED`, IFSC, Account Number, Bank Name).
  - Enable **Show Account Number on Invoices** for B2B NEFT/RTGS payments.
  - Create dedicated **Cash / Petty Cash** journal and **Clearing Journals** (`Razorpay Clearing`, `Shiprocket COD Clearing`) so gateway and COD settlements reconcile 1-to-1 with payouts before hitting the main Bank journal!

### 12. Accounting Journals Setup
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Accounting → Configuration → Journals`
- **Required Journals:**
  - `Customer Invoices` (`INV/` FY prefix — e.g. `ZOE/26-27/0001` compliant with Indian GST 16-char limit)
  - `Credit Notes` (`RINV/` — used for refunds & RTO credit notes)
  - `Vendor Bills` (`BILL/` — supplier purchases, job-work, rent, agencies)
  - `Main Current Bank` (`BNK1/`)
  - `Razorpay / Payment Gateway` (Bank-type clearing journal)
  - `COD Courier Remittance` (Bank-type clearing journal)
  - `Cash / Petty Cash` (`CSH1/`)
  - `Miscellaneous / Payroll / Partner Capital` (`MISC/`)
  - `Inventory Valuation` (Phase 2 automated valuation if Perpetual Inventory is enabled)

### 13. Multi-Company Configuration (if required)
- **When:** `Phase 5` (Do **NOT** split in Phases 1–4) | **Layer:** `Odoo 20.0 Built-In`
- **Strategy ([`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md), [`PARTNER_VERTICAL_ACCESS_CONTROL.md`](./PARTNER_VERTICAL_ACCESS_CONTROL.md), [`MULTIPLE_STORES_CLOTHING_GADGETS.md`](./MULTIPLE_STORES_CLOTHING_GADGETS.md)):**
  - **Phases 1–4:** Run **Single Company (`ZOEE GLOBAL PRIVATE LIMITED`)**. Separate apparel lines, retail stores, and partners cleanly using **Brands, Warehouses, Sales Teams, Analytic Plans, and `ir.access` rules**—splitting companies too early breaks shared inventory transfers, shared capital/bank reconciliation, and doubles GST returns.
  - **Phase 5 Trigger:** Create a second Odoo Company (e.g., `ZOEE TECH & GADGETS PRIVATE LIMITED` or separate GSTIN entity) **only if** legal liability, investor equity split, or separate GST vertical compliance demands independent statutory books. If kept under the same GSTIN/Pvt Ltd, use **Multi-Website (`website_id`)** + separate Warehouse + separate Brand instead of Multi-Company.

### 14. Brand Management – `FAIRTAG`, `ZOIRA`, `GADGETS`
- **When:** Scaffolded in `Phase 1` (`FAIRTAG`, `ZOIRA`), Activated at `Phase 5 Gate 4` (`GADGETS`) | **Layer:** `Odoo 20.0 Built-In` + `Manual Business Config` / `OCA`
- **Architecture:** Odoo 20.0 Community has no built-in `product.brand` table out-of-the-box. Implement **Brand** cleanly across **four synchronized dimensions** so Phase 1 stays simple and Phase 3–5 Multi-Brand reporting works effortlessly:
  1. **Product Attribution:** Add a `Brand` attribute (`FAIRTAG`, `ZOIRA`, `GADGETS` with `Variants Creation = Never` / informative attribute) OR install OCA `product_brand` when moving to Phase 3 so every SKU clearly carries its Brand.
  2. **SKU Naming Standard ([`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md)):** Prefix every SKU with brand code:
     - `FTG-...` → **`FAIRTAG`** (e.g., streetwear / fashion / mass apparel line)
     - `ZOR-...` → **`ZOIRA`** (e.g., ladies ethnic / festive / curated fashion line)
     - `GDG-...` → **`GADGETS`** (Phase 5 electronics / mobile & smart accessories)
  3. **eCommerce & Storefronts (Step 42):** Map `FAIRTAG` and `ZOIRA` either as featured Collections/Websites and keep `GADGETS` on its own isolated `website_id` when Gate 4 (`≥ ₹30L/mo apparel`) unlocks.
  4. **Analytic Plan (`Brand`):** Attach Analytic Account `Brand: FAIRTAG`, `Brand: ZOIRA`, `Brand: GADGETS` to Products/Sales/Ad Spend so P&L shows net profitability per brand!

### 15. Branch & Department Setup
- **When:** Core Departments `Phase 1`, Physical Store Branches `Phase 3–4` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Employees → Configuration → Departments` (+ `Inventory → Configuration → Warehouses` for physical locations)
- **Configure:**
  - **Departments:**
    - `Executive & Finance` (Founders / Partners + CA interface)
    - `Product, Design & Sourcing` (Ladies, Men, Kids, Custom Fabrics, Phase 5 Gadgets)
    - `Warehouse, QC & Fulfillment` (Surat Warehouse Hub)
    - `Sales, CRM & Customer Support / COD Desk`
    - `E-Commerce & Growth Marketing`
    - `Retail Operations` (Store #1 Surat in Phase 3 → Stores #2–#5 in Phase 4)
  - **Branches:** In Odoo Community, physical branches (Surat HQ Warehouse, Store #1 Citylight, Store #2 Satellite Ahmedabad, Store #3 Mumbai, etc.) are modeled via **Warehouses (`stock.warehouse`) + POS Configs (`pos.config`) + Analytic Accounts (`Branch`)** (or multiple GSTIN Companies only if registered in different states—e.g. Maharashtra/Delhi GSTIN requires either separate Warehouse GSTIN fiscal setup or Multi-Company GST registration in Odoo).

### 16. User Management
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` + [`AUTHENTICATION_AND_GOOGLE_OAUTH.md`](./AUTHENTICATION_AND_GOOGLE_OAUTH.md)
- **Path:** `Settings → Users & Companies → Users`
- **Configure:**
  - Create individual **Internal Users** (never share one login across staff so Chatter audit logs track who confirmed COD, packed stock, or edited prices).
  - **Portal Users (`base.group_portal`):** Auto-created for storefront customers via `auth_signup` (`/web/signup`).
  - **Google Sign-In (`auth_oauth`):** Install `auth_oauth`, configure Google Cloud OAuth 2.0 Client ID in `Settings → General Settings → Integrations → OAuth Authentication` (see [`AUTHENTICATION_AND_GOOGLE_OAUTH.md`](./AUTHENTICATION_AND_GOOGLE_OAUTH.md) for HTTPS domain rules).

### 17. User Groups & Access Rights
- **When:** `Phase 1 (Day-1)` & Expanded per Role in `Phase 2–5` | **Layer:** `Odoo 20.0 Built-In` + [`PARTNER_VERTICAL_ACCESS_CONTROL.md`](./PARTNER_VERTICAL_ACCESS_CONTROL.md)
- **Role Matrix (`Settings → Users → Access Rights`):**
  - **Founders / Admins:** Full Settings, Administration, Show Full Accounting Features, Sales/Purchase/Inventory Administrators.
  - **Vertical Partners / Category Managers (`Ladies`, `Children`, `Custom Stitches`, `GADGETS`):** Sales Manager + Inventory User restricted by `ir.access` domain to their Product Category / Brand / Sales Team (see Step 61).
  - **Warehouse & QC Packer:** `Inventory / User` only (no Accounting, no Cost Price/Margin visibility unless authorized, no Vendor Bills).
  - **COD & Support Executive:** `Sales / User: Own Documents Only` (or All Documents) + `Support Ticket User` (`custom_erp` `custom.support.ticket`).
  - **Retail Store Cashier (Phase 3):** `Point of Sale / User` only (locked to their branch POS terminal).
  - **Accountant / CA:** `Accounting / Accountant` (`Show Full Accounting Features`), Read-only on Sales/Inventory.

### 18. Employee Configuration
- **When:** `Phase 1 (Founders + First Ops Hires)` → Scaled `Phase 2–4` | **Layer:** `Odoo 20.0 Built-In` (`hr`, `hr_expense`, `hr_attendance`, `hr_holidays`, `hr_recruitment`)
- **Path:** `Employees → Employees`
- **Configure:**
  - Create Employee records for both Founders/Partners (link to `Related User`, Department, Work Email, Bank Account for reimbursements) and staff (`Packer`, `Support Agent`, `Tailor/QA`, `Store Staff`).
  - Enable **Attendance (`hr_attendance`)** for warehouse/store shifts in Phase 2–3, **Time Off (`hr_holidays`)** for leave tracking, and **Recruitment (`hr_recruitment`)** at Phase 3+ hiring.
  - Note: Odoo Enterprise `hr_payroll` is **not** in Community; track Partner salaries in Accounting via `Vendor Bills` / `hr_expense` / MISC journal in Phases 1–2 ([`PARTNER_ACCOUNTING_AND_SALARIES.md`](./PARTNER_ACCOUNTING_AND_SALARIES.md)) and evaluate OCA `payroll` in Phase 3+ (`>5` staff).

---

## Stage C — Partners, Master Catalog, SKU Standards & Pricing (Steps 19–28)

### 19. Contacts Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` (`contacts`)
- **Path:** `Contacts`
- **Configure:**
  - Enforce clean Indian address formatting: `Street`, `City`, `State` (critical for IGST vs CGST/SGST!), `ZIP` (6-digit PIN code), `Country = India`, `Phone` / `Mobile` (10-digit WhatsApp number), `GSTIN` (`Tax ID` — required for B2B vendors & wholesale buyers).
  - Activate Contact Tags (`VIP Customer`, `Repeat Buyer`, `COD High-Risk / RTO`, `B2B Boutique`, `Surat Mill`, `Stitching Job-Worker`, `Brand: FAIRTAG`, `Brand: ZOIRA`).

### 20. Customer Management
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` + `Custom Addon (Included)`
- **Configure:**
  - Deduplicate customers by Mobile Number / Email (website guest/portal signups link cleanly to `res.partner`).
  - **RTO Risk Flagging:** Tag serial COD refusers with `COD High-Risk / RTO` and pair with `custom_erp` `x_cod_verification_status` (`cancelled_rto_risk`) to block automated COD dispatch for repeat offenders.
  - **B2B / Wholesale Tiers:** Assign `B2B Wholesale` Pricelist and `15/30 Days` Payment Terms only to vetted boutique buyers (default D2C customers stay `Immediate Payment`).

### 21. Vendor Management
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Purchase → Orders → Vendors`
- **Configure:**
  - Onboard Surat wholesalers, textile mills (`Fabrics`), stitching/job-work units (for Phase 3 `mrp_subcontracting`), courier partners (`Shiprocket`, `Delhivery`), packaging suppliers, and Meta/Google/Razorpay service vendors.
  - Record each vendor's **GSTIN**, **Vendor Payment Terms** (`Immediate`, `50% Advance / 50% Dispatch`, `Net 30`), **Delivery Lead Time**, and **Bank Account Details** for NEFT batches.

### 22. Product Category Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Custom Addon (Included)` + `Odoo 20.0 Built-In`
- **Pre-seeded Internal Categories (`addons/custom_erp/data/product_category_data.xml`):**
  - `All / Apparel` (Phase 1 primary focus)
    - `Ladies` (`Kurtis & Kurti Sets`, `Sarees`, `Co-ord Sets & Dress Materials`)
    - `Men` (Phase 3 activation)
    - `Kids` (Phase 4 activation)
    - `Fabrics` (Unstitched / Custom Stitches)
    - `Footwear` (Phase 5)
    - `Accessories & Gadgets` (Phase 5)
- **Pre-seeded eCommerce Public Categories (`addons/custom_store/data/public_category_data.xml`):** `Ladies` (`Kurtis & Kurti Sets`, `Sarees`, `Co-ord Sets & Dress Materials`, `Dupattas & Fabrics`), `Men`, `Kids` (add `Gadgets` only on the Gadgets website in Phase 5).
- **Important Setting on Categories:** Configure default **Income Account**, **Expense/COGS Account**, and Costing Method (`AVCO` / `Average Cost` or `FIFO` when enabling automated inventory valuation in Phase 2).

### 23. Product Attribute Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Custom Addon (Included)` + `Odoo 20.0 Built-In`
- **Pre-seeded Attributes (`addons/custom_erp/data/product_attribute_data.xml`):**
  - `Size` (`XS`, `S`, `M`, `L`, `XL`, `XXL`, `3XL`, `Free Size`) — `Variant Creation: Instantly`
  - `Color` (`Black`, `Maroon`, `Navy Blue`, `Mustard`, `Emerald Green`, `Pastel Pink`, `Ivory`, `Wine`, `Teal`, `Off-White`) — Color swatch display
  - `Fabric Type` (`Pure Cotton`, `Rayon 14kg`, `Chanderi Silk`, `Georgette`, `Muslin`, `Linen`, `Crepe`, `Organza`, `Silk Blend`) — `Variant Creation: Never` (filter/spec attribute without exploding SKU count)
- **Add for Brand Segregation:** Create `Brand` attribute (`FAIRTAG`, `ZOIRA`, `GADGETS`) with `Variant Creation: Never` (unless OCA `product_brand` is installed).
- **Phase 5 Gadgets Attributes:** Add `Storage / Capacity`, `Compatibility`, `Warranty Period` (`6 Months`, `1 Year`) keeping `Variant Creation: Instantly` only for sellable SKUs.

### 24. Product Brand Configuration
- **When:** `Phase 1 (FAIRTAG, ZOIRA)` → `Phase 5 (GADGETS)` | **Layer:** `Manual Business Config` / `OCA`
- **How to keep `FAIRTAG`, `ZOIRA`, and `GADGETS` clean across ERP:**
  - Maintain clear Brand tags/attributes (`Brand = FAIRTAG`, `Brand = ZOIRA`, `Brand = GADGETS`) on every `product.template`.
  - Use SKU prefixes `FTG-`, `ZOR-`, `GDG-`.
  - Assign Website visibility (`website_id`) so `FAIRTAG`/`ZOIRA` apparel products never accidentally appear on the `GADGETS` storefront (and vice versa).
  - Map `Analytic Distribution` or Sales Teams per Brand for clean margin reporting.

### 25. Product Creation
- **When:** `Phase 1 (Day-1)` (Start small: **50–100 core Ladies SKUs** per `SCALING_ROADMAP.md`) | **Layer:** `Odoo 20.0 Built-In` + `Custom Addon (Included)`
- **Odoo 20.0 Rule:** Select **Product Type = `Goods`** and toggle **`Track Inventory`** ON for stocked/dropshipped physical items; use `Service` only for shipping fees, stitching labor charges, or gift wrap.
- **Required Fields on Every Product (`product.template`):**
  - `Name` (Clean SEO title: e.g., `Zoira Maroon Embroidered Rayon Kurti Set`)
  - `Internal Category` + `eCommerce Categories` + `Website`
  - `Sales Price` (MRP / Selling Price) & `Cost`
  - `Customer Taxes` (`5% GST` if `≤ ₹2,500`, `18% GST` if `> ₹2,500`; watch `custom_erp` **`x_gst_slab_warning`** banner!)
  - `HSN/SAC Code` (`l10n_in_hsn_code`, e.g. `6204`, `5407`)
  - `custom_erp` Apparel Tab fields: `x_fabric`, `x_fit_type` (`regular`, `relaxed`, `slim`, `oversized`, `unstitched`), `x_wash_care`, `x_dispatch_days` (default `2`), `Weight` (for Shiprocket volumetric/weight slab!).
  - High-resolution product photos (primary + gallery per color variant).

### 26. SKU & Barcode Configuration
- **When:** `Phase 1 (Day-1 SKU rule)` → `Phase 2–3 (Thermal Hang-Tag Barcode Labels)` | **Layer:** `Odoo 20.0 Built-In` (`barcodes`)
- **Mandatory SKU (`default_code`) Convention ([`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md)):**
  `[BRAND]-[CAT]-[STYLE]-[COLOR]-[SIZE]`
  - Example: `ZOR-KRT-001-MRN-M` (`ZOIRA`, `Kurti`, Style `001`, `Maroon`, Size `M`)
  - Example: `FTG-TSH-014-BLK-L` (`FAIRTAG`, `T-Shirt`, Style `014`, `Black`, Size `L`)
  - Example: `GDG-EAR-002-WHT-STD` (`GADGETS` Phase 5)
- **Barcodes (`barcode` field per `product.product` variant):**
  - Generate unique **EAN-13** (if listing on Amazon/Myntra/retail chains requiring GS1/EAN) or **Code-128** barcodes matching SKU on garment hang-tags & polybags.
  - Phase 2–3 Warehouse/POS scanning: Configure USB/Bluetooth barcode scanners in `Settings → Inventory → Barcode Scanner` (`barcodes` built-in, plus OCA `stock_barcodes` when warehouse volume hits Phase 3–4).

### 27. Unit of Measure Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` (`uom`)
- **Path:** `Settings → Inventory / Sales → Units of Measure`
- **Configure:**
  - Enable **Units of Measure** (`uom`) so **Purchase UoM** and **Sales UoM** can differ cleanly:
    - **Readymade Garments / Gadgets:** `Units` (1 `Pc`) — Purchase in `Pack of 4/6 Sets` or `Dozens` (`12 Units`) if Surat wholesalers bill in sets, auto-converting to individual size SKUs on receipt!
    - **Unstitched / Custom Stitches (`Fabrics`):** Configure `Meters` (`m`, Reference Unit) + `Roll / Than (25m / 50m)` for buying meters from Surat mills and selling `2.5m` / `3m` cuts.

### 28. Pricelist Configuration
- **When:** `Phase 1 (Day-1 D2C MRP)` → `Phase 2–4 (Wholesale / VIP / Flash Sale)` | **Layer:** `Odoo 20.0 Built-In` + `sale_loyalty`
- **Path:** `Sales → Products → Pricelists`
- **Configure:**
  - `D2C Public INR Pricelist` (Default Website pricelist — Indian MRP tax-included display, `FAIRTAG` / `ZOIRA` standard pricing).
  - `B2B Wholesale / Boutique Tier` (Volume discount: `e.g., ≥ 20 pcs = 25% off` or fixed wholesale price rules).
  - `Festival / Flash Sale Pricelist` (Optional date-bound discounts alongside **Promotions & Coupons** in `loyalty` / `website_sale_loyalty` e.g., `PREPAID5` extra 5% off prepaid UPI orders to reduce COD RTO!).

---

## Stage D — Inventory, Warehousing & Procurement (Steps 29–35)

### 29. Warehouse Configuration
- **When:** `Phase 1 (Virtual/Starter + Dropship)` → `Phase 2 (Surat Warehouse)` → `Phase 3–4 (Store #1–#5 + Central Hub)` | **Layer:** `Odoo 20.0 Built-In` (`stock`, `stock_dropshipping`)
- **Path:** `Inventory → Configuration → Warehouses`
- **Configure:**
  - **`WH` (`Surat Main Warehouse`):** Primary hub for D2C dispatch (`FAIRTAG` & `ZOIRA`).
    - Phase 1: 1-step Incoming & 1-step Outgoing + **`Dropship` Route** (`stock_dropshipping`) enabled for zero-inventory supplier test styles.
    - Phase 2–4: Upgrade `WH` to **2-step Receipt** (`Input / QC → Stock`) and **2-step/Pick-Pack-Ship** (`Pick → Pack → Output`) so damaged Surat supplier lots are caught before shelf put-away!
  - **`ST1`..`ST5` (Phase 3–4):** One Warehouse per retail store (`Surat Store #1`, etc.) supplied via **Resupply from `WH` (`Central Hub`)**.
  - **`WH-GDG` (Phase 5):** Dedicated Gadgets Warehouse / Rack zone separated from garment lint/dust and tracked under serial/warranty rules.

### 30. Inventory Locations Setup
- **When:** `Phase 1–2 (Core)` → `Phase 3–4 (Bin/Rack & Quarantine)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Inventory → Configuration → Locations` (enable `Storage Locations` & `Multi-Step Routes` in Inventory Settings)
- **Location Tree under `WH`:**
  - `WH/Stock` (Sellable Shelf Stock, optionally subdivided `WH/Stock/Ladies`, `WH/Stock/Men`, `WH/Stock/Fabrics`, `WH/Stock/Bin-A1`)
  - `WH/Input-QC` (Incoming goods awaiting Stitch/Size check)
  - `WH/Output-Dispatch` (Packed parcels awaiting Shiprocket/Delhivery pickup)
  - `WH/RTO-Quarantine` (Dedicated physical/logical location for Returned/RTO parcels **never** directly resold until QC-cleared!)
  - `WH/Vendor-Return` / `Virtual Locations/Scrap` (Defective items for supplier credit claim or clearance)

### 31. Stock Operation Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` + `Custom Addon (Included)`
- **Operation Types (`Inventory → Configuration → Operation Types`):**
  - `Receipts` (`WH/IN/`) — Set barcode/QC mandatory before validating.
  - `Delivery Orders` (`WH/OUT/`) — Uses **`custom_erp` `stock.picking` Packing & QC workflow**:
    - `x_packing_status`: `Pending QC & Pack` → `QC Verified` → `Packed & Labelled` → `Handed to Courier` / `RTO Received`
    - `x_qc_verified`: Checkbox verifying size, stitching, and garment hang-tag before handover
    - `x_dispatch_note`: Courier AWB / pickup note
  - `Internal Transfers` (`WH/INT/`) — Used for Central Hub → Store #1–#5 replenishments in Phase 3–4.
  - `Dropships` (`DS/`) — Used in Phase 1 when supplier ships directly to customer.
  - `Returns` — Return Picking back to `WH/RTO-Quarantine`.

### 32. Reordering Rules Setup
- **When:** `Phase 2 (Own Stock)` → `Phase 3–4 (Multi-Store Automated Replenishment)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Inventory → Operations → Replenishment` (or smart button `Reordering Rules` on each product)
- **Configure:**
  - Set `Min Quantity` (safety stock + supplier lead-time buffer, e.g., `5 pcs`) and `Max Quantity` (`e.g., 25 pcs`) on fast-moving Phase 2–3 SKUs (`FAIRTAG` / `ZOIRA` bestsellers).
  - Configure Store → Central Hub automated **Internal Transfer Reordering Rules** in Phase 3–4 so retail POS stores never run dry on popular sizes (`M`, `L`, `XL`).
  - Leave **slow/seasonal trial garments** on manual `Make to Order` / `Buy` or no reordering rule to avoid dead inventory!

### 33. Purchase Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` (`purchase`, `purchase_stock`, `purchase_requisition`)
- **Path:** `Purchase → Configuration → Settings`
- **Configure:**
  - **Bill Control:** Set default to **`On Received Quantities`** (3-way check: Purchase Order ↔ Warehouse Receipt ↔ Vendor Bill) so you never pay a mill/supplier for short-shipped pieces.
  - **Blanket Orders / Purchase Agreements (`purchase_requisition`):** Enable in Phase 3 when committing fabric rolls or own-label manufacturing lots (`ZOIRA` / `FAIRTAG` contract manufacturing) with staggered deliveries.
  - **Subcontracting (`mrp` + `mrp_subcontracting`):** Enable in Phase 3 when buying raw fabric (`Fabrics`) and sending it to Surat tailoring job-workers to return finished kurtis/shirts!

### 34. Vendor Pricelist Setup
- **When:** `Phase 1 (Core Suppliers)` → `Phase 2–3 (MOQ & Multi-Vendor)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** Product → `Purchase` tab → `Vendors` (`product.supplierinfo`)
- **Configure:**
  - For each SKU/style, add Primary Supplier (and Backup Supplier in Phase 2+) with:
    - `Vendor`
    - `Vendor Product Code` (mill/wholesaler style number)
    - `Minimum Quantity` (MOQ e.g. `10 pcs` or `1 set`)
    - `Price` (Negotiated wholesale rate)
    - `Delivery Lead Time (Days)` (e.g., `3 days` Surat local, `7 days` Jaipur/Delhi)
    - `Validity Dates` (important for seasonal cotton/fabric price changes)

### 35. Purchase Approval Workflow
- **When:** `Phase 2–3` (Solo founders in Phase 1; enforced once Buyers/Merchants join) | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `Purchase → Configuration → Settings → Purchase Order Approval`
- **Configure:**
  - Enable **Purchase Order Approval** and set monetary threshold (e.g., Merchandisers can raise RFQs up to `₹25,000`; anything `> ₹25,000` moves to `To Approve` state requiring **Founder / Purchase Manager** confirmation before converting into a binding PO!).
  - Pair with `Step 56` (`Automated Actions` alert on high-value POs).

---

## Stage E — Sales, CRM, Multi-Website Storefront, Payments, Shipping & POS (Steps 36–49)

### 36. Sales Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` + `Custom Addon (Included)`
- **Path:** `Sales → Configuration → Settings` + [`addons/custom_erp/models/sale_order.py`](../addons/custom_erp/models/sale_order.py)
- **Configure:**
  - Install/active: `sale_management`, `sale_stock`, `sale_stock_margin`, `sale_product_matrix`, `loyalty`, `sale_loyalty`.
  - **Margin Visibility (`sale_stock_margin`):** Track real gross margin per Sales Order line.
  - **Product Grid Entry (`sale_product_matrix`):** Essential for fast WhatsApp & B2B wholesale orders (enter `S/M/L/XL` quantities in one matrix pop-up).
  - **`custom_erp` Omnichannel & COD Controls on `sale.order`:**
    - `x_sales_channel`: `Website (D2C)`, `WhatsApp Business`, `Instagram / Social`, `Myntra`, `Ajio`, `Amazon`, `Flipkart`, `Meesho`, `Retail Store`, `B2B Wholesale`.
    - `x_payment_mode`: `Prepaid (UPI / Card / Netbanking)`, `Cash on Delivery (COD)`, `Partial / Split`.
    - **COD Confirmation Queue:** New COD orders default `x_cod_verification_status = Pending Verification`; support calls/WhatsApps the customer and clicks **`Confirm COD`** (`action_confirm_cod`) or **`Flag High RTO Risk`** (`action_flag_cod_rto_risk`) before warehouse packing!

### 37. Sales Teams Setup
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In`
- **Path:** `CRM / Sales → Configuration → Sales Teams`
- **Teams Structure:**
  1. `Website / D2C Auto-Channel` (`FAIRTAG` & `ZOIRA` online orders)
  2. `WhatsApp & Instagram Social Desk` (conversational orders & COD confirmations)
  3. `B2B Wholesale & Boutique Inquiries`
  4. `Marketplaces Desk` (Phase 2+: Myntra, Ajio, Amazon, Flipkart, Meesho)
  5. `Gadgets Sales Team` (Phase 5 Gate 4)
- Link each team to a Team Leader, Pipeline alias email, and Monthly Revenue Target.

### 38. Quotation Templates
- **When:** `Phase 1 (B2B / Custom Boutique)` | **Layer:** `Odoo 20.0 Built-In` (`sale_management`, `sale_pdf_quote_builder`)
- **Path:** `Sales → Configuration → Quotation Templates` (enable in Sales Settings)
- **Configure:**
  - `B2B Boutique Starter Assortment` (pre-populated Kurti/Set MOQ lines, `50% Advance` payment terms, GSTIN note, `7-day` quote expiration).
  - `Custom Stitches / Made-to-Measure Order` (measurement notes + `5–7 days` dispatch SLA + non-returnable custom-stitch terms).
  - Enable **Online Signature & Online Payment** on Quotation Templates so B2B buyers can approve & pay deposit via Razorpay link directly.

### 39. Sales Order Workflow
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` + `Custom Addon (Included)`
- **Standard End-to-End D2C Flow:**
  1. Order captured (`Website Checkout` / `WhatsApp Manual SO` / `Marketplace import`) with `x_sales_channel` & `x_payment_mode` set.
  2. **Branch A — Prepaid (Razorpay):** Payment confirmed → SO auto-confirms → Warehouse picks & QC-packs (`WH/OUT`).
  3. **Branch B — COD:** SO created with `x_cod_verification_status = pending` → Support verifies address/intent via WhatsApp/Call → Clicks `Confirm COD` → Warehouse receives pick task (`WH/OUT`).
  4. **Dispatch & Invoice:** Packing status moves `Pending QC & Pack` → `QC Verified` (`x_qc_verified = True`) → `Packed & Labelled` → `Handed to Courier` (`AWB` recorded) → Automatic or manual Customer Invoice (`out_invoice`, carrying `x_sales_channel` & `x_payment_mode`).
  5. **Exception — RTO:** If undelivered, click `Mark RTO` (`action_mark_rto` + `x_rto_reason`), receive returned parcel into `WH/RTO-Quarantine`, and post Credit Note if already invoiced.

### 40. CRM Configuration
- **When:** `Phase 1 (Day-1 for WhatsApp/Instagram/Wholesale)` | **Layer:** `Odoo 20.0 Built-In` (`crm`) + `Custom Addon (Included)`
- **Path:** `CRM` + [`addons/custom_erp/models/crm_lead.py`](../addons/custom_erp/models/crm_lead.py)
- **Pipeline Stages:** `New Inquiry` → `Qualified / Size & Budget Checked` → `Quotation / Payment Link Sent` → `Negotiation / COD Follow-up` → `Won` (converts directly to SO) / `Lost` (with reason: Price, Out of Stock, Delivery Delay).
- **`custom_erp` CRM Fields:**
  - `x_inquiry_channel`: `Website Inquiry`, `Instagram DM / Reel`, `WhatsApp Business`, `Marketplace Query`, `B2B / Boutique Wholesale`, `Customer Referral`.
  - `x_product_interest`: `Ladies Wear`, `Men's Wear`, `Kids' Wear`, `Unstitched Fabrics`, `Footwear & Accessories`, `Multi-Category / Bulk`.
  - `x_preferred_size`: Bust/size/custom stitching notes.
- **Lead Assignment Rules:** Auto-route `B2B Wholesale` to the Wholesale Team and `Ladies/Custom` WhatsApp DMs to dedicated vertical reps.

### 41. Website Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` (`website`) + `Custom Addon (custom_store)`
- **Path:** `Website → Configuration → Settings` & Live Website Builder (`/`)
- **Configure:**
  - Primary Website (`Shop Apparel` / `ZOIRA & FAIRTAG`) pre-styled by `addons/custom_store/` (`header.xml`, `homepage.xml`, `footer.xml`, `custom_store.scss`).
  - Built-in custom policy pages included in `custom_store`: `/size-guide`, `/shipping-policy`, `/return-policy`, `/support`, plus Blog (`website_blog`) and Live Chat (`im_livechat`).
  - Configure SEO Meta Title/Description, Favicon, Google Analytics / Meta Pixel ID in `Website → Configuration → Settings → SEO / Tracking` (critical for Phase 1–2 Meta ROAS tracking!).
  - See [`WEBSITE_AND_ECOMMERCE_EDITING.md`](./WEBSITE_AND_ECOMMERCE_EDITING.md) for when to edit via live Website Builder vs XML/SCSS in `addons/custom_store/`.

### 42. Multi-Website Setup
- **When:** `Phase 3–5` (Brand sites for `FAIRTAG` & `ZOIRA` if split, and **mandatory** at `Phase 5 Gate 4` for `GADGETS`) | **Layer:** `Odoo 20.0 Built-In` + [`MULTIPLE_STORES_CLOTHING_GADGETS.md`](./MULTIPLE_STORES_CLOTHING_GADGETS.md)
- **Architecture Rule:** Keep a single clean apparel site in Phase 1. When adding a second storefront (`FAIRTAG` vs `ZOIRA` vs `GADGETS`):
  1. Go to `Website → Configuration → Websites → New`:
     - Website 1: Apparel Store (`fairtag.in` / `zoira.in` or unified apparel domain)
     - Website 2 (Phase 5): Gadgets Store (`gadgets.<domain>`)
  2. Set strict per-website defaults: **Company**, **Default Pricelist**, **Customer Country Group**, **Default Warehouse** (`WH-GDG` for Gadgets), **Payment Providers**, and **Delivery Methods**.
  3. On every `Product`, `Public Category`, `Banner/Page`, and `Payment/Shipping Method`, explicitly assign `Website = <Target Website>` (avoid leaving Gadgets products unassigned/`All Websites`, or clothing buyers will see chargers!).

### 43. eCommerce Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` (`website_sale`, `website_sale_stock`, `website_sale_loyalty`) + `Custom Addon (custom_store)`
- **Path:** `Website → Configuration → Settings → Shop - Products & Checkout`
- **Configure:**
  - **Inventory Display (`website_sale_stock`):** Show real-time available stock or *"Out of Stock"* blocking (`Prevent Sale if Out of Stock`) so you never oversell a last `M` piece!
  - **Shop Filters (`shop_templates.xml`):** Enable Attribute Filters (`Size`, `Color`, `Fabric Type`, `Brand`) & Price Slider.
  - **Custom PDPs (`CUSTOM_PRODUCT_PDP.md`):** Use standard Builder blocks for normal SKUs, and per-product QWeb template / HTML description blocks for flagship launches.
  - **Checkout UX (`checkout_templates.xml`, `cart_templates.xml`):** Express mobile checkout (`Name, Phone, PIN, Street, Payment`), Guest Checkout enabled alongside OTP/Account Signup (`auth_signup`), and **Promo Code box** (`PREPAID5`).

### 44. Website Domain Configuration
- **When:** `Phase 1 (Go-Live)` + `Phase 3–5 (Extra Brand Domains)` | **Layer:** `Odoo 20.0 Built-In` + `Infra / Nginx`
- **Configure:**
  1. Point DNS `A` record (`@`, `www`, and later `gadgets.`) to the Production VPS Public IP.
  2. In Odoo `Website → Configuration → Websites → Domain`, enter exact domain (`https://zoira.in`, `https://fairtag.in`, `https://gadgets....`).
  3. In Production Nginx ([`deploy/nginx.conf`](../deploy/nginx.conf)), terminate SSL/TLS (`Certbot` / Let's Encrypt), configure `server_name` blocks for each domain, pass `Host` and `X-Forwarded-Proto https` headers to Odoo `8069` (and `/websocket` to `8072`), and ensure `proxy_mode = True` in production `odoo.conf` so Odoo matches incoming `Host` headers to the exact `website_id`!

### 45. Website Product Publishing
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In`
- **Pre-Publish Checklist (per SKU):**
  - `Sales Price > 0` and `Website` field assigned (`FAIRTAG`/`ZOIRA` vs `GADGETS`)
  - `eCommerce Categories` assigned (e.g., `Ladies / Kurtis & Kurti Sets`)
  - At least 3 crisp photos + Variant images per `Color`
  - Apparel Specs filled (`x_fabric`, `x_fit_type`, `x_wash_care`, `x_dispatch_days`, Size Chart link `/size-guide`)
  - On-hand Stock `> 0` (or `Continue Selling` explicitly chosen for Dropship/Made-to-Order)
  - Toggle **Is Published** (`website_published = True`) ON (or bulk publish via `Website → eCommerce → Products → Action → Publish`).

### 46. Payment Provider Integration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` (`payment_razorpay`, `payment_custom`)
- **Path:** `Website / Accounting → Configuration → Payment Providers`
- **Configure:**
  1. **Razorpay (`payment_razorpay`):**
     - Enter `Key ID`, `Key Secret`, and `Webhook Secret` from Razorpay Dashboard.
     - Test in **Test Mode** first (`UPI`, `Cards`, `Netbanking`), validate webhook callback `/payment/razorpay/webhook` receives `payment.captured`, then switch to **Enabled (Live)**.
     - Link **Payment Journal** to your `Razorpay Clearing` journal (Step 12).
  2. **Cash on Delivery (`payment_custom` — Wire Transfer / Custom COD Provider):**
     - Rename display label cleanly to `Cash on Delivery (COD)` (`Verify via Phone/WhatsApp before dispatch`).
     - Optionally cap COD eligibility (`Minimum/Maximum Amount` or exclude `Orders > ₹5,000`) and pair with `PREPAID5` coupon incentive to boost prepaid share (`> 40%`).

### 47. Shipping Method Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` (`delivery`, `stock_delivery`)
- **Path:** `Website / Inventory → Configuration → Shipping Methods`
- **Configure:**
  - `Free Standard Delivery (Prepaid / Above ₹999)` — Rule-based fixed price `₹0` above `₹999`, else `₹79`.
  - `Standard Express Shipping` — Fixed or Weight-slab (`0–500g = ₹69`, `500g–1kg = ₹99`, `+₹40/500g`).
  - `COD Handling Fee` (Optional `₹49` / `₹50` extra when COD is selected to discourage non-serious COD orders).
  - Assign Website & Product availability cleanly (`GADGETS` may use insured/fragile shipping rules in Phase 5).

### 48. Delivery Carrier Integration
- **When:** `Phase 1 (Shiprocket CSV/Manual AWB)` → `Phase 2 (API / Webhook Sync)` → `Phase 4 (Multi-Courier Rate Shopping)` | **Layer:** `External / Custom Connector` + `Odoo 20.0 Built-In`
- **Rollout Plan ([`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md)):**
  - **Phase 1:** Export confirmed/COD-verified orders (`WH/OUT`) to **Shiprocket / Delhivery**, generate AWB, paste AWB & tracking number back onto `stock.picking` (`Carrier Tracking Ref` + `x_dispatch_note`), and notify buyer via email/WhatsApp.
  - **Phase 2+:** Integrate Shiprocket/Delhivery REST API connector (sync Order → Auto-AWB & Label print inside Odoo → Webhook auto-updates `Delivered` / `NDR` / `RTO Initiated` → auto-triggers `action_mark_rto`).

### 49. POS Configuration (if required)
- **When:** **`Phase 3 (Gate 2: Store #1 Surat)`** — Keep **UNINSTALLED / DORMANT** in Phases 1–2! | **Layer:** `Odoo 20.0 Built-In` (`point_of_sale`, `l10n_in_pos`, `pos_razorpay`, `pos_sale`)
- **Details:** [`MODULES_AND_DB_PORTABILITY.md`](./MODULES_AND_DB_PORTABILITY.md)
- **Activation Sequence at Phase 3:**
  1. Install `point_of_sale`, `l10n_in_pos`, `pos_razorpay`, `pos_sale` via `upgrade.bat` or `Apps`.
  2. Configure `Point of Sale → Configuration → Point of Sale` per retail branch (`Surat Store #1` linked to Warehouse `ST1`).
  3. Enable **POS Razorpay Terminal / UPI QR (`pos_razorpay`)**, Cash Register journal, Thermal 80mm Receipt Printer (`GSTIN + HSN + CGST/SGST` via `l10n_in_pos`), Customer Loyalty/Phone lookup, and **`pos_sale`** (to settle or exchange online orders in-store!).

---

## Stage F — Invoicing, Expenses, Analytics, Reporting, Automation & Support (Steps 50–60)

### 50. Invoice Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` (`account`, `l10n_in`, `l10n_in_edi`) + `Custom Addon (Included)`
- **Configure:**
  - **Invoicing Policy:** Set products to **`Delivered Quantities`** (or `Ordered Quantities` only for prepaid D2C instant invoicing; `Delivered Quantities` prevents invoicing unverified/cancelled COD orders!).
  - **`custom_erp` Extensions (`addons/custom_erp/models/account_move.py` + `views/report_invoice.xml`):** Propagates `x_sales_channel` and `x_payment_mode` from `sale.order` onto `account.move` (`Customer Invoices` & `Credit Notes`) so GST sales registers break out D2C vs Myntra vs Amazon vs Store POS automatically.
  - **B2B / GST Threshold:** Enable `l10n_in_edi` for IRN + QR-code e-Invoicing once turnover/B2B rules apply.

### 51. Expense Management
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` (`hr_expense`) + [`PARTNER_ACCOUNTING_AND_SALARIES.md`](./PARTNER_ACCOUNTING_AND_SALARIES.md)
- **Path:** `Expenses` (`hr_expense`)
- **Configure:**
  - Expense Categories: `Travel & Sourcing`, `Packaging & Market Supplies`, `Staff Meals & Store Petty Cash`, `Courier / Local Porter`, `Partner Out-of-Pocket Reimbursements`.
  - **Flow:** Employee/Partner snaps receipt → Submits Expense Report → Manager/Co-Partner approves → Accountant posts Journal Entry & reimburses via Bank/Partner Current Account.
  - **Note on Formal Purchases (`Rent, Meta Ads, Agencies, Software`):** Record via `Accounting → Vendors → Bills` (not `hr_expense`) so GST Input Tax Credit (`ITC`) and TDS (`Section 194C/194J`) are tracked properly for your CA!

### 52. Analytic Accounting Configuration
- **When:** `Phase 1 (Basic Tags)` → `Phase 2–5 (Full Brand & Store P&L)` | **Layer:** `Odoo 20.0 Built-In` (`analytic`)
- **Path:** `Accounting → Configuration → Analytic Accounting → Analytic Plans & Accounts` (enable `Analytic Accounting` in Accounting Settings)
- **Configure Plans:**
  - **Plan 1 — `Brand`:** `FAIRTAG`, `ZOIRA`, `GADGETS`
  - **Plan 2 — `Channel`:** `Website D2C`, `Marketplaces`, `Wholesale B2B`, `Retail POS`
  - **Plan 3 — `Store / Branch` (Phase 3–4):** `Surat HQ`, `Store #1 Citylight`, `Store #2..#5`
- Set **Analytic Distribution Models** so every sale, purchase, ad bill, and rent bill splits automatically into real contribution margin by Brand, Channel, and Store!

### 53. Financial Reporting
- **When:** `Phase 1 (Monthly GST + P&L)` → `Phase 2–4 (OCA Reports)` | **Layer:** `Odoo 20.0 Built-In` + `OCA Extensions`
- **Built-in Reports (`Accounting → Reporting`):**
  - `Profit and Loss`, `Balance Sheet`, `Partner Ledger`, `Aged Receivable / Payable`, `General Ledger`, `Tax Report` + **Indian GST Reports** (`l10n_in`: GSTR-1 B2B/B2CS/HSN summaries, GSTR-3B).
- **Community vs Enterprise Note ([`ROADMAP_MODULE_STATUS.md`](./ROADMAP_MODULE_STATUS.md)):** Odoo Community lacks full Enterprise `account_accountant` dynamic drill-down and automated bank sync. At Phase 2–3, add **OCA `account_financial_report`**, **OCA `account_reconcile_oca`**, and **OCA `mis_builder`** (or connect Metabase/Excel exports) for CA-ready multi-period financial packs, bank reconciliation rules, and budgets.

### 54. Email Server Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` (`mail`)
- **Path:** `Settings → Technical → Email → Outgoing Mail Servers` & `Incoming Mail Servers` (activate Developer Mode)
- **Configure:**
  - **Outgoing SMTP (`Google Workspace` / `Zoho Mail` / `Amazon SES` / `SendGrid`):** Set SMTP host, port (`587 STARTTLS` or `465 SSL`), authenticated sender (`noreply@zoira.in` / `orders@fairtag.in`), and configure **SPF, DKIM, and DMARC** DNS TXT records so order confirmations, invoices, and support replies never land in Spam.
  - **Catchall & Alias Domain:** Set `mail.catchall.domain` (`Settings → General Settings → Custom Email Servers`) so customer replies to order emails and `support@...` / `sales@...` automatically append to Odoo Chatter / `custom.support.ticket` / CRM Leads via Incoming Mail Server (IMAP/POP).

### 55. Automated Actions Configuration
- **When:** `Phase 1–2 (Core Alerts)` → `Phase 3–5 (Scale Workflows)` | **Layer:** `Odoo 20.0 Built-In` (`base_automation`)
- **Path:** `Settings → Technical → Automation → Automation Rules` (Developer Mode)
- **Recommended High-ROI Rules:**
  1. **COD SLA Reminder:** If `sale.order` stays `x_cod_verification_status == 'pending'` for `> 4 hours`, schedule an urgent Activity for the Support Desk.
  2. **RTO Auto-Risk Tagging:** When a customer reaches `≥ 2` orders with `x_is_rto == True`, automatically tag `res.partner` with `COD High-Risk / RTO`.
  3. **Invoice Email Auto-Send:** Upon posting a Prepaid Website Invoice, automatically trigger the Order Invoice Email template.
  4. **Low Stock Reorder Ping:** Notify Purchasing when fast-mover `qty_available` drops below safety threshold.
  5. **Support Ticket Auto-Acknowledge:** When `custom.support.ticket` is created from `/support` or `/my/tickets`, assign round-robin agent and send ticket reference email.

### 56. Approval Workflow Configuration
- **When:** `Phase 2–4` | **Layer:** `Odoo 20.0 Built-In` + `OCA / Custom State Guards`
- **Community Reality Note:** Odoo's standalone `approvals` app is Enterprise-only. Implement multi-tier approvals natively using Community mechanisms:
  - **Purchase Approvals:** Built-in `Purchase Order Approval` amount threshold (Step 35).
  - **Expense Approvals (`hr_expense`):** Built-in `Draft → Submitted → Approved → Posted` team-leader + accountant flow.
  - **High-Discount / Credit Note Approvals:** Lock Salesperson max discount (e.g., `> 10%`) or Credit Note posting via `base_automation` + `ir.access` restrictions requiring Sales/Accounting Manager approval.
  - **Custom `Approvals` (Phase 4+):** Install OCA `tier_validation` (`base_tier_validation`) if formal multi-level sign-off chains are needed on POs, Bills, or Stock Write-offs.

### 57. Document Management
- **When:** `Phase 1 (Chatter Attachments)` → `Phase 4 (Structured DMS)` | **Layer:** `Odoo 20.0 Built-In` (`mail` / `ir.attachment`) + `OCA DMS`
- **Community Reality Note:** Odoo Enterprise `documents` app is not in Community.
  - **Phases 1–3:** Attach GST Vendor Bills, Packaging Artwork PDFs, Courier Manifests, Custom Stitch Measurement Sheets, and Partner KYC directly to each record's **Chatter** (stored safely inside `data/filestore/zoeemasterdb/` and backed up automatically by `save_db.bat`!).
  - **Phase 4+ (`5+ stores`, heavy PDFs/design files):** Install **OCA `dms`** (`Document Management System`) or link structured Google Drive / S3 folders per SKU & Store Compliance Certificate.

### 58. Helpdesk Configuration
- **When:** `Phase 1 (Day-1)` | **Layer:** `Custom Addon (Included)` + `Odoo 20.0 Built-In` (`im_livechat`)
- **Included Custom Engine ([`addons/custom_erp/models/support_ticket.py`](../addons/custom_erp/models/support_ticket.py) + `addons/custom_store/`):**
  - Model: `custom.support.ticket` (sequence from `support_sequence_data.xml`), accessible in Backend menu, Website `/support` page, and Customer Portal `/my/tickets`.
  - Pre-configured Ticket Types & Links: Order Reference, Size Exchange / Return, Payment / Refund Issue, Shipping Delay, Customer Chatter thread.
  - Live Chat (`im_livechat`): Embedded Website chat widget routed to Support users during business hours.
- **Phase 3+ Upgrade:** Keep using `custom.support.ticket` or migrate/extend with **OCA `helpdesk_mgmt`** + WhatsApp Business API integration (`Interakt` / `Wati` / `AiSensy`) when ticket volume exceeds `50+/day`.

### 59. Return & Refund Workflow
- **When:** `Phase 1 (Day-1)` | **Layer:** `Odoo 20.0 Built-In` + `Custom Addon (Included)` → `Phase 2–3 OCA RMA`
- **Two Separate Apparel Return Flows (Never mix them!):**
  1. **RTO (Courier Failed Delivery — Customer Never Received):**
     - Mark SO with **`Mark RTO`** (`custom_erp` `action_mark_rto` + `x_rto_reason`: `size_issue`, `customer_unavailable`, `refused_cod`, `fake_order`, `damaged`, `other`).
     - Receive physical parcel into **`WH/RTO-Quarantine`**, inspect garment & hang-tag (`x_qc_verified`), restock clean items to `WH/Stock`, and cancel/credit uncollected COD invoice (no cash refund!).
  2. **Customer Return / Size Exchange (Post-Delivery via `/support` or `/my/tickets`):**
     - Support raises Reverse Pickup in Shiprocket/Delhivery + creates **Return Picking** on `WH/OUT` pointing to `WH/RTO-Quarantine`.
     - **Size Exchange:** Once QC passes, issue Store Credit / Coupon (`loyalty`) or confirm ₹0 replacement SO linked to original order.
     - **Refund:** Issue **Credit Note (`out_refund`)** and process refund via Razorpay Refund API (for Prepaid) or Bank NEFT/UPI payout (only for verified COD deliveries!)—never refund without physical QC pass!
- **Phase 2–3 Scaling:** Install **OCA `rma`** for formal portal RMA numbers, automated exchange shipments, and defect analytics by vendor/fabric.

### 60. Dashboard Configuration
- **When:** `Phase 1 (Built-in)` → `Phase 3–4 (BI / Executive)` | **Layer:** `Odoo 20.0 Built-In` (`spreadsheet_dashboard`) + `External BI`
- **Built-in Odoo 20.0 Dashboards (`Dashboards` app):**
  - Customize KPI Spreadsheets (`spreadsheet_dashboard`) & saved Pivot/Graph favorites tracking:
    - **Daily Sales by `x_sales_channel`** (`Website`, `WhatsApp`, `Myntra`, `Retail POS`)
    - **Prepaid vs COD Ratio & COD Confirmation Backlog** (`x_payment_mode`, `x_cod_verification_status`)
    - **RTO Rate % by SKU, Pin/State, & Reason** (`x_is_rto`, `x_rto_reason`)
    - **Gross Margin by Brand (`FAIRTAG`, `ZOIRA`, `GADGETS`)** & Inventory Days-on-Hand
- **Phase 4+ Executive BI:** Connect read-only **Metabase** or **Looker Studio** directly to a read-replica of PostgreSQL for multi-store cohorts, CAC vs LTV, and supplier defect trends.

---

## Stage G — Security, Backups, Migration, Custom Code, Testing & Production Go-Live (Steps 61–67)

### 61. Security Rules & Record Rules
- **When:** `Phase 1 (Base)` → `Phase 2–5 (Partner Vertical & Multi-Store Isolation)` | **Layer:** `Odoo 20.0 Built-In` + `Custom Addon` + [`PARTNER_VERTICAL_ACCESS_CONTROL.md`](./PARTNER_VERTICAL_ACCESS_CONTROL.md)
- **Odoo 20.0 Architecture Warning:** Odoo 20.0 **replaced `ir.rule` with unified `ir.access`** (`addons/custom_erp/security/ir.access.csv`)! Do not write legacy `<record model="ir.rule">` XML for Odoo 20.0.
- **Configured Rules (`addons/custom_erp/security/ir.access.csv`):**
  - Internal users (`base.group_user`) have CRUD on `custom.support.ticket`.
  - Portal users (`base.group_portal`) are scoped strictly to `[('partner_id', 'child_of', [user.commercial_partner_id.id])]`.
  - Multi-company filter `['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`.
- **Partner Vertical Isolation Pattern (Ladies / Kids / Gadgets / Custom Stitches):** Add `ir.access` domain rules + Sales Team + Warehouse restrictions so each vertical manager sees only their own Category/Brand Orders, Products, Tickets, and Stock without touching sister verticals' sensitive vendor rates or customer lists.

### 62. Backup Configuration
- **When:** `Phase 1 (Day-1 — Mandatory before Go-Live)` | **Layer:** `Infra / DevOps` ([`scripts/odoo_ctl.py`](../scripts/odoo_ctl.py), [`deploy/backup_db.sh`](../deploy/backup_db.sh))
- **Golden Rule of Odoo Backups:** **NEVER back up PostgreSQL alone!** Invoices, logos, product images, and QWeb assets live in `data/filestore/<db>/`. Both DB and `filestore/` MUST match at the same point in time.
- **Local / Golden Snapshot Workflow:**
  - Save full DB + `filestore/<db>` + manifest zip into `backups/`:
    ```powershell
    .\save_db.bat
    ```
  - Restore onto any machine/fresh PostgreSQL cleanly via:
    ```powershell
    .\load_db.bat
    ```
- **Production Automated Backup ([`deploy/backup_db.sh`](../deploy/backup_db.sh)):**
  - Schedule daily VPS cron (`02:30 IST`) running `deploy/backup_db.sh` (`pg_dump -Fc` + `filestore/zoeemasterdb` tar/zip).
  - Sync backups off-server to encrypted **AWS S3 / Backblaze B2 / Cloudflare R2** with retention (`7 daily`, `4 weekly`, `12 monthly`) and test a quarterly restore onto staging via `load_db.bat`!

### 63. Data Import & Migration
- **When:** `Phase 1 (Clean Launch)` & `Phase 2–4 (Catalog / Store Expansions)` | **Layer:** `Odoo 20.0 Built-In` (`base_import`)
- **Path:** List View → Gear Menu (`⚙`) → `Import records` (`.csv` or `.xlsx`)
- **Strict Import Dependency Order (breaking this causes missing links/errors):**
  1. `Accounting`: Missing COA Accounts & Taxes (usually seeded by `l10n_in` + Step 8)
  2. `Contacts`: Vendors first (with GSTIN & State), then B2B/Existing Customers
  3. `Inventory`: Warehouses, Locations & Product Categories (pre-seeded by `custom_erp`)
  4. `Attributes`: Size / Color / Brand values (pre-seeded by `custom_erp`)
  5. `Products`: Product Templates (`Name`, `Category`, `HSN`, `Taxes`, `x_fabric`, `x_fit_type`) → then Product Variants (with exact `[BRAND]-[CAT]-[STYLE]-[COLOR]-[SIZE]` SKU & Barcode!)
  6. `Vendor Pricelists`: Link SKU → Vendor → Cost Price & MOQ
  7. `Opening Inventory`: `Inventory → Operations → Physical Inventory` import `Quantity` + `Cost` (`AVCO` value) on Opening Balance cutover date
  8. `Opening Accounting Balances`: Opening Trial Balance (AR/AP open bills/invoices, Bank balance, Partner Capital) checked with your CA!

### 64. Custom Module Development
- **When:** `Phase 1 (Foundation Included)` → `Phase 2–5 (Targeted Extensions)` | **Layer:** `Custom Addon` (`addons/custom_erp/`, `addons/custom_store/`)
- **Strict Engineering Rules:**
  - **Never edit core files under [`odoo/addons/`](../odoo/addons/).** Put all business logic in `addons/custom_erp/` and all storefront UI/templates in `addons/custom_store/` (plus future modular addons under `addons/`—e.g. `custom_shiprocket`, `custom_marketplace_sync`, `custom_gadgets` at Gates 2–4).
  - Keep **Odoo 20.0 conventions**: `<list>` instead of `<tree>`, `ir.access.csv` instead of `ir.rule`, `Goods` + `Track Inventory`, `env.company` awareness.
  - **Upgrade workflow after every XML/Python/JS edit:**
    ```powershell
    .\upgrade.bat
    ```
    (Or selectively: `.\upgrade.bat -u custom_erp,custom_store` and restart `odoo-bin`).

### 65. Integration Testing
- **When:** `Phase 1 (Pre-Launch)` & Every Module Upgrade | **Layer:** `QA / Verification`
- **Mandatory Technical Checks Before Live Traffic:**
  1. **Clean Module Load & Upgrade Test:**
     ```powershell
     .\.venv\Scripts\python.exe .\odoo\odoo-bin -c .\odoo.conf -d zoeemasterdb -u custom_erp,custom_store --stop-after-init
     ```
  2. **Odoo Test Tags (if tests added) & Python Syntax Check.**
  3. **End-to-End Integration Smoke Tests:**
     - **Storefront Checkout (Prepaid):** Add Kurti variant (`Size M`) → Apply promo code → Pay via Razorpay Test Mode → Verify webhook marks transaction `Done` → Verify SO confirmed + `WH/OUT` picking created + Invoice carries `x_sales_channel = website` & `x_payment_mode = prepaid`.
     - **Storefront Checkout (COD) & RTO:** Place COD order → Verify `x_cod_verification_status = pending` → Run `Confirm COD` → Simulate `Mark RTO` + Return to `WH/RTO-Quarantine`.
     - **GST Threshold Check:** Test item `≤ ₹2,500` vs `> ₹2,500` → Verify Intra-state (`CGST+SGST`), Inter-state (`IGST`), and `x_gst_slab_warning` behavior.
     - **Email & Support Flow:** Submit `/support` ticket → Confirm email arrives via SMTP and ticket appears in `/my/tickets`.
     - **DR Restore Drill:** Run `save_db.bat`, then restore onto a scratch DB with `load_db.bat test_restore` (then clean up with `remove_db.bat test_restore -y`) to verify DB + images survive intact!

### 66. User Acceptance Testing (UAT)
- **When:** `Phase 1 (Pre-Launch)` & Before Every Phase Gate Rollout | **Layer:** `Business Ops`
- **Persona Sign-Off Checklist:**
  - [ ] **Founder / Admin:** Reviews Trial Balance, Partner Capital & Current accounts, Margin per SKU, and Brand separation (`FAIRTAG` / `ZOIRA`).
  - [ ] **Category / Vertical Manager (Ladies / Custom Stitches):** Creates new style with variants (`S..XL`), verifies hang-tag SKU/barcode, publishes to `/shop`, confirms category isolation works (`Step 61`).
  - [ ] **Warehouse & QC Staff:** Receives supplier PO, completes `x_qc_verified`, packs `WH/OUT` parcel, prints Packing Slip & Tax Invoice, executes a Return to `WH/RTO-Quarantine`.
  - [ ] **Support / COD Executive:** Works pending COD call queue, handles a CRM WhatsApp inquiry to quotation, replies to a `/my/tickets` case.
  - [ ] **Accountant / CA:** Validates GSTR-1 invoice export, HSN summary, `x_sales_channel` filter on `account.move`, and Razorpay/COD clearing reconciliation.
  - [ ] **Retail Cashier (Phase 3 UAT):** Scans garment barcode in POS, processes Razorpay UPI QR + Cash split bill, executes in-store return.

### 67. Production Deployment
- **When:** `Phase 1 Go-Live` → Scaled at `Phase 3–5` | **Layer:** `Infra / DevOps` ([`docker-compose.prod.yml`](../docker-compose.prod.yml), [`deploy/`](../deploy/))
- **Production Stack (`deploy/`):**
  - `odoo-prod-db`: `postgres:16-alpine` (`odoo-prod-db-data`)
  - `odoo-prod-web`: Built from [`deploy/Dockerfile`](../deploy/Dockerfile) (`python:3.12-slim-bookworm`, `postgresql-client`, `wkhtmltopdf` for PDF Tax Invoices & Delivery Slips, [`deploy/entrypoint.sh`](../deploy/entrypoint.sh))
  - `odoo-prod-nginx`: `nginx:1.27-alpine` ([`deploy/nginx.conf`](../deploy/nginx.conf), ports `80` / `443`, proxies HTTP `8069` & `/websocket` `8072`)
- **Production Hardening Checklist (Critical Differences from Local Dev):**
  1. Generate a **strong production `.env`** (`DB_PASSWORD`, strong `ADMIN_PASSWORD` replacing `zoeeadmin`, `ODOO_DB=zoeemasterdb`, `ODOO_WORKERS=2`–`4` depending on VPS CPU cores, `ODOO_CRON_THREADS=1`).
  2. Set `list_db = False` and `proxy_mode = True` in production Odoo config, configure `dbfilter = ^zoeemasterdb$` (or domain regex if Multi-Website routes single DB).
  3. Transfer golden snapshot created via `save_db.bat` to VPS and restore DB + `filestore/zoeemasterdb` into `odoo-prod-db` & `odoo-prod-web-data`.
  4. Start production stack (`docker compose -f docker-compose.prod.yml up -d --build`) and configure HTTPS SSL certificates (Let's Encrypt / Cloudflare Origin SSL) on Nginx.
  5. Switch Razorpay from **Test Keys → Live Keys**, verify live `₹1` UPI checkout + refund, verify live SMTP emails & SPF/DKIM, verify Shiprocket order pickup, and activate cron for [`deploy/backup_db.sh`](../deploy/backup_db.sh).
  6. Future code deployments: Pull git updates → run [`deploy/upgrade_prod.sh`](../deploy/upgrade_prod.sh) (auto-backups before upgrading!).

---

## Roadmap Phase Rollout Summary (`SCALING_ROADMAP.md` Alignment)

Use this matrix so you follow **the exact 1→67 engine order** without over-engineering Day 1:

| Phase & Revenue Gate ([`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md)) | Primary Business Focus | Active Steps from `1 → 67` | Explicitly Deferred (Do NOT Turn On Yet) |
| :--- | :--- | :--- | :--- |
| **Phase 1: Surat Seed** (`₹0–3L/mo`, Days 1–90) | Single store Ladies Apparel (`ZOIRA` / `FAIRTAG`), dropship + starter stock, D2C + WhatsApp/Instagram, COD verification | **Core Engine:** `1–12`, `14` (Apparel scaffold), `15–28` (Base/50–100 SKUs), `29–31` (1 WH + Dropship), `33–34`, `36–41`, `43–48`, `50–55`, `58–67` | POS (`49`), Multi-Website (`42`), Multi-Company (`13`), `GADGETS`, Subcontracting (`33`), Complex Approvals (`56`) |
| **Phase 2: Own Stock & Marketplaces** (`₹3–15L/mo`, Gate 1 passed) | Surat Warehouse (`WH`), Myntra/Ajio/Amazon/Flipkart/Meesho feeds, Shiprocket/Delhivery API, Barcodes & QC | Expand `29–35` (2-step QC, Reordering rules, Multi-vendor), `48` (Courier API), `52–53` (Analytic Channel P&L + OCA reports), `59` (OCA RMA) | Physical Store POS (`49`), Multi-Company (`13`), `GADGETS` |
| **Phase 3: Own Label & Store #1** (`₹15–50L/mo`, Gate 2 passed) | `FAIRTAG` & `ZOIRA` own-label tailoring (`mrp_subcontracting`), **Men's Wear**, **Retail Store #1 (POS)** | Activate `33` (`mrp_subcontracting`, `purchase_requisition`), `35` (PO Approval), `49` (`point_of_sale`, `l10n_in_pos`, `pos_razorpay`), `18` (Attendance/Payroll OCA), `42` (Brand microsite if needed) | Stores #2–#5, `GADGETS`, Multi-Company (`13`) |
| **Phase 4: Central Hub & 5 Stores** (`₹50L–1.5Cr/mo`, Gate 3 passed) | Central Hub → 5 Stores replenishment, **Kids Wear**, Multi-City/State inventory, Executive BI | Scale `15–17` (`61` Partner Vertical Isolation across Ladies/Kids/Stitches), `29–32` (Central Hub → `ST1..ST5` transfer routes), `56–57` (`tier_validation`, DMS), `60` (Metabase BI), Redis/Workers (`67`) | `GADGETS` (Wait for Gate 4!) |
| **Phase 5: Lifestyle & `GADGETS` Expansion** (`₹1.5Cr+/mo`, Gate 4 passed) | `GADGETS` Brand & Storefront, Fabrics/Footwear/Accessories scale, optional Multi-Company | Unlock **`13`** (Multi-Company only if legally required), **`14` & `42` & `44`** (`GADGETS` dedicated Website + Domain + `WH-GDG` + Serial/Warranty Tracking + `repair`), Multi-currency (`6`) | — (Full Engine Active) |

---

## Related Project Guides

- [`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md) — Business gates, Surat strategy, Red Flags, hiring, and infrastructure capacity plans
- [`ROADMAP_MODULE_STATUS.md`](./ROADMAP_MODULE_STATUS.md) — Live Odoo 20.0 Community module coverage vs OCA extensions
- [`ARCHITECTURE_AND_CUSTOM_ERP.md`](./ARCHITECTURE_AND_CUSTOM_ERP.md) — Daily commands, `custom_erp` models, and repo structure
- [`MODULES_AND_DB_PORTABILITY.md`](./MODULES_AND_DB_PORTABILITY.md) — Activating dormant apps (`point_of_sale`) and portable DB snapshots
- [`PARTNER_ACCOUNTING_AND_SALARIES.md`](./PARTNER_ACCOUNTING_AND_SALARIES.md) — 2-Partner Indian accounting, capital, expenses & salaries
- [`PARTNER_VERTICAL_ACCESS_CONTROL.md`](./PARTNER_VERTICAL_ACCESS_CONTROL.md) — Vertical isolation for Ladies, Children, `GADGETS`, and Custom Stitches
- [`MULTIPLE_STORES_CLOTHING_GADGETS.md`](./MULTIPLE_STORES_CLOTHING_GADGETS.md) — Multi-Website, `website_id`, Nginx domains & Gadgets launch rules
- [`AUTHENTICATION_AND_GOOGLE_OAUTH.md`](./AUTHENTICATION_AND_GOOGLE_OAUTH.md) — Portal signup & Google OAuth setup
- [`WEBSITE_AND_ECOMMERCE_EDITING.md`](./WEBSITE_AND_ECOMMERCE_EDITING.md) & [`CUSTOM_PRODUCT_PDP.md`](./CUSTOM_PRODUCT_PDP.md) — Storefront and PDP customization

