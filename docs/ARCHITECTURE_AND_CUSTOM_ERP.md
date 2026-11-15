# Repository Architecture, `custom_erp` & CLI Commands

> Companion to [`README.md`](../README.md) and [`OPERATIONS_GUIDE.md`](./OPERATIONS_GUIDE.md).

---

## 1. Repository Layout (`odoo/` vs `addons/`)

This project keeps upstream Odoo source completely separate from your business code so you can pull Odoo updates safely and deploy cleanly to production:

| Directory | Tracked in Git? | Purpose |
| :--- | :---: | :--- |
| `odoo/` | No (`.gitignore`) | Clean upstream `odoo/odoo` clone (`20.0`). **Never edit files here.** |
| `addons/custom_erp/` | Yes | **Backend ERP & Phase-1 Operations** (`Custom Apparel ERP & Phase-1 Operations`, `v20.0.2.0.0`). |
| `addons/custom_store/` | Yes | **Website, eCommerce, Checkout, Portal & Support UI** (`Custom Store Website & eCommerce`, `v20.0.2.0.0`). |
| `addons/custom_enterprise/` | Yes | **Custom Enterprise Suite** (`Custom Enterprise Suite (Community Edition)`, `v20.0.1.0.0`) — custom Community implementations of Enterprise apps. |
| `addons/custom_accounting_pro/` | Yes | **Custom Accounting Pro** (`v20.0.1.0.0`) — Interactive Bank Reconcile, PDF/Text Bill OCR, Auto-Asset on Post, Consolidation & Cash Flow, Tax Lock & Equity Cap Table. |
| `addons/custom_comms/` | Yes | **Custom Communications** (`v20.0.1.0.0`) — WhatsApp Business Cloud API & Webhook, VoIP Call Logger, and Frontdesk Visitor Kiosk (`/frontdesk`). |
| `addons/custom_omnichannel/` | Yes | **Custom Omnichannel** (`v20.0.1.0.0`) — eCommerce `/shop` Subscriptions & Rentals auto-provisioning, Drawn Canvas e-Sign & Stamped PDF Certificates. |
| `addons/custom_operations_ui/` | Yes | **Custom Operations UI** (`v20.0.1.0.0`) — Shop Floor Tablet (`/shopfloor`), Camera Barcode PWA (`/barcode`), Timesheets & Timers, Calendar Timelines, Formula Spreadsheets & Studio App Builder. |
| `addons/custom_scaling_ops/` | Yes | **Custom Scaling Ops** (`v20.0.1.0.0`) — RMA Size Exchanges, Shiprocket/Delhivery Courier AWB & Webhook, Marketplace Catalog/Order CSV Sync, Apparel Hang-Tag PDFs, `/barcode/push`, Warranty Claims & Franchise Inter-Company PO → SO Sync. |
| `.env` | No (`.gitignore`) | Single source of truth for PostgreSQL credentials, `ODOO_PORT`, `ODOO_BRANCH`, `ODOO_DB`, and worker settings (see `.env.example`). |
| `odoo.conf` | Yes | Structural defaults (`http_interface`, `addons_path`, `data_dir`, `list_db`). |
| `data/` & `backups/` | No (`.gitignore`) | Runtime config (`data/odoo.runtime.conf`), filestore (`data/filestore/<db>/`), sessions, and `.zip` backups. |

---

## 2. What `addons/custom_erp/` Includes

`addons/custom_erp` is your upgrade-safe backend ERP master addon:

* **Reproducible Phase-1 Dependency Stack** ([`__manifest__.py`](../addons/custom_erp/__manifest__.py)): Installs `sale_management`, `sale_stock_margin`, `loyalty`, `sale_loyalty`, `purchase`, `stock`, `stock_delivery`, `stock_dropshipping`, `account`, `l10n_in*`, `payment_razorpay`, `payment_custom`, `crm`, `im_livechat`, `mass_mailing`, `portal`, `website_blog`, and `website_sale_stock`.
* **Day-1 Apparel Master Data** (`addons/custom_erp/data/`): Apparel category tree (`Apparel / Ladies / Men / Kids`, `Fabrics`, `Footwear`, `Accessories & Gadgets`), `Size` / `Color` / `Fabric Type` attributes, and support ticket numbering sequence.
* **Product & Indian Apparel GST Slab Advisory** ([`models/product_template.py`](../addons/custom_erp/models/product_template.py)): Adds `x_fabric`, `x_fit_type`, `x_wash_care`, `x_dispatch_days`, and `x_gst_slab_warning` (checks Indian companies on apparel/footwear HSN prefixes `61`, `62`, `63`, `5407`, `5208`, `64` against the ₹2,500 5% vs 18% GST threshold).
* **Sales Channel, COD & RTO Workflow** ([`models/sale_order.py`](../addons/custom_erp/models/sale_order.py)): Tracks `x_sales_channel` (Website, WhatsApp, Instagram, Myntra, Ajio, Amazon, Flipkart, Meesho, Retail Store, B2B Wholesale), `x_payment_mode`, COD verification queue (`action_confirm_cod`, `action_flag_cod_rto_risk`), and RTO status/reasons (`action_mark_rto`).
* **Warehouse Packing & QC** ([`models/stock_picking.py`](../addons/custom_erp/models/stock_picking.py)): Adds `x_packing_status`, `x_qc_verified`, and `x_dispatch_note` on stock transfers.
* **Invoicing & GST Invoice Layout** ([`models/account_move.py`](../addons/custom_erp/models/account_move.py), [`views/report_invoice.xml`](../addons/custom_erp/views/report_invoice.xml)): Copies `x_sales_channel` and `x_payment_mode` onto customer invoices/credit notes and customizes QWeb invoice metadata.
* **CRM Lead Fields** ([`models/crm_lead.py`](../addons/custom_erp/models/crm_lead.py)): Adds `x_inquiry_channel`, `x_product_interest`, and `x_preferred_size`.
* **Community Support & Size-Exchange Tickets** ([`models/support_ticket.py`](../addons/custom_erp/models/support_ticket.py)): Provides `custom.support.ticket` (Kanban/List/Form, stages `new` → `in_progress` → `waiting_customer` → `resolved` → `closed`, `/my/tickets/<id>` portal access, and stat buttons on `res.partner` and `sale.order`).

---

## 2b. What `addons/custom_enterprise/` Includes

`addons/custom_enterprise` builds custom Odoo 20.0 Community equivalents of Odoo Enterprise applications without per-user license fees:

* **Enterprise Finance (`models/account_enterprise.py`):** Dynamic P&L & Balance Sheet wizard (`custom.financial.statement.wizard`), Fixed Assets & Straight-Line/WDV Depreciation schedules (`custom.asset`), Deferred Revenue / Prepaid Expense recognition (`custom.deferred.schedule`), Live GL/Analytic Budgets (`custom.account.budget`), and Bank/UPI/Razorpay CSV Import & Auto-Reconciliation Rules (`custom.bank.import.wizard`, `custom.bank.reconcile.rule`).
* **Helpdesk+ (`models/helpdesk_enterprise.py`):** Round-Robin Support Teams (`custom.support.team`), SLA Policies & Breach Tracking (`custom.support.sla`), Canned Responses (`custom.support.canned.response`), and Customer CSAT Ratings (`/my/tickets/<id>/rate`).
* **HR Payroll, Appraisals & Referrals (`models/hr_enterprise.py`):** Indian salary structure (`IN_STD`), Employee Payslips (`custom.hr.payslip`) with QWeb PDF report and Accounting Journal Entry posting, Employee Appraisals & KPI Goals (`custom.hr.appraisal`), and Employee Referrals (`custom.hr.referral`).
* **Approvals & DMS (`models/approvals_documents.py`):** Multi-step Approval Requests (`custom.approval.request`) and Central Document Management (`custom.document`) with folders, tags, expiry dates, and 1-click Vendor Bill / Ticket / Approval / e-Sign creation.
* **Barcode Scan Console, Quality Control, PLM & MPS (`models/inventory_quality_plm.py`):** Interactive Barcode Scan Sessions (`custom.barcode.session`) for transfers & cycle counts, QC Points & Checks (`custom.quality.check`) with `stock.picking.button_validate()` guard, Garment/Gadget PLM Tech Packs & ECOs (`custom.plm.techpack`, `custom.plm.eco`), and Master Production & Replenishment Schedule (`custom.mrp.mps`).
* **Sign, Subscriptions, Rentals, Marketing, Social, Field Service, Planning, Knowledge & Appointments (`models/sales_services_marketing.py`, `models/knowledge_appointments.py` & `controllers/sign.py`):** Public token e-Signature portal (`/my/sign/<token>`), Recurring Subscriptions with auto-invoicing cron (`custom.subscription`), Rental Bookings (`custom.rental.order`), Drip Marketing Automation (`custom.marketing.campaign`), Multi-brand Social Planner (`custom.social.post`), Field Service Tasks (`custom.field.service.task`), Employee Shift Planning (`custom.planning.shift`), Internal SOP Knowledge Base (`custom.knowledge.article`), and Public Appointments (`/appointments`, `custom.appointment.booking`).
* **Executive KPIs & Studio-Lite (`models/kpi_studio.py`):** Cross-ERP KPI Snapshots (`custom.kpi.snapshot`) and guided `x_studio_*` custom field + form view builder (`custom.studio.field.wizard`).

---

## 2c. Modular Enterprise Extension Addons

Four focused addons plus `custom_scaling_ops` in `addons/` extend `custom_enterprise` and `custom_store` to cover remaining Enterprise &amp; scaling capabilities:

* **`addons/custom_accounting_pro/` (`models/accounting_pro.py`):** Interactive Bank Reconciliation (`custom.bank.reconcile.wizard`, `custom.bank.reconcile.line`), PDF & Text Vendor Bill OCR (`custom.bill.ocr.wizard` using `PyPDF2`), Auto-Asset creation when vendor bill lines carry `x_asset_category_id` (`AccountMoveAssetHook._post`), Multi-Company Consolidation & Cash Flow (`custom.consolidation.wizard`), Period & Tax Date Locks (`custom.tax.lock.wizard`), and Equity Cap Table (`custom.equity.holder`, `custom.equity.grant`).
* **`addons/custom_comms/` (`models/comms.py`, `controllers/main.py`):** WhatsApp Business Cloud API connector, approved templates, local sandbox simulator & webhook (`/whatsapp/webhook`), VoIP Call Logger & COD Phone Verification (`custom.voip.call`) with `sale.order` header actions, and Frontdesk Visitor Reception Kiosk (`/frontdesk`, `custom.frontdesk.visitor`).
* **`addons/custom_omnichannel/` (`models/omnichannel.py`, `controllers/main.py`):** `/shop` product flags (`x_is_subscription`, `x_is_rental`), rental date booking route (`/shop/rental/book`), automatic provisioning of `custom.subscription` & `custom.rental.order` on `sale.order.action_confirm()`, HTML5 `<canvas>` freehand signature capture on `/my/sign/<token>`, and stamped PDF certificate generation (`/my/sign/<token>/pdf` using `reportlab`, `PyPDF2`, and `PIL`).
* **`addons/custom_operations_ui/` (`models/operations_ui.py`, `controllers/main.py`):** Shop Floor Workcenter Tablet Kiosk (`/shopfloor`, `custom.shopfloor.workorder`), Mobile Camera `BarcodeDetector` & Web Audio Barcode PWA (`/barcode`, `/barcode/lookup`), Employee Timesheets & Start/Stop Timers (`custom.timesheet.entry`), Calendar timeline views on `custom.planning.shift` & `custom.rental.order`, Formula Spreadsheets (`custom.spreadsheet.sheet`, `custom.spreadsheet.cell` with `=SUM`, `=ODOO_SALES_30D()`, `=ODOO_MRR()`, etc.), and Studio-Lite Custom App/Model Creator (`custom.studio.app.wizard` provisioning `x_*` models, `ir.access`, views, action, and menu).
* **`addons/custom_scaling_ops/` (`models/scaling_ops.py`, `controllers/main.py`, `views/report_hangtag.xml`):** Returns & Size-Exchange RMAs (`custom.rma.request`) creating Return Pickings, Replacement SOs, and Credit Notes; Shiprocket/Delhivery Courier Aggregator (`custom.courier.config`, `stock.picking.action_generate_awb`, `/courier/webhook`) & COD Pincode Blocklist (`custom.courier.pincode.rule`); Myntra/Ajio/Amazon/Flipkart/Meesho Catalog Feed Export & Order CSV Import (`custom.marketplace.channel`, `custom.marketplace.import.wizard`); Apparel Hang-Tag Code128 QWeb PDF labels; `/barcode/push` Camera Scan-to-Session Push; Gadget Warranty Claims (`custom.warranty.claim`); and Franchise Inter-Company PO → SO auto-mirroring (`custom.intercompany.rule`).

---

## 3. Daily Project Commands (Windows Dev)

| Script / Command | Action |
| :--- | :--- |
| `docker compose up -d` | Manually starts the standalone shared PostgreSQL container (`shared-postgres`) |
| `.\.venv\Scripts\python.exe odoo\odoo-bin -c odoo.conf` | Manually launches Odoo directly against PostgreSQL using `odoo.conf` |
| `.\upgrade.bat` | Takes backup, pulls clean `odoo/`, upgrades installed custom addons (`-u`) |
| `.\upgrade.bat --skip-pull` | Skips `git pull` in `odoo/` and upgrades installed `addons/` modules |
| `.\upgrade.bat --skip-pull --install --modules <name>` | Installs a newly added module from `addons/` (`-i`) |
| `.\save_db.bat` | Saves SQL + `manifest.json` + `filestore` into `backups/*.zip` |
| `.\load_db.bat` | Restores a `.zip` / `.sql` backup into PostgreSQL + `data/filestore/` |
| `.\remove_db.bat` | Drops a single selected database and removes its `data/filestore/<db>` folder without affecting other DBs |

