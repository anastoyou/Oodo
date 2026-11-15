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

