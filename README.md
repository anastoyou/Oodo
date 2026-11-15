# Odoo 20.0 ERP — Production-Ready Custom Addons & `.env` Architecture

This project runs **Odoo 20.0** directly from upstream [`odoo/odoo`](https://github.com/odoo/odoo) (kept completely unmodified in `odoo/`) alongside custom version-controlled addons in `addons/` and a Linux VPS production stack in `deploy/`.

All database credentials, ports, workers, and MCP settings live in **one file: `.env`** (see `.env.example` for the committed template).

---

## 📁 Project Layout

- **`.env` / `.env.example`**: Single source of truth for DB credentials (`DB_*`), Odoo settings (`ADMIN_PASSWORD`, `ODOO_PORT`, `ODOO_BRANCH`, `ODOO_ENV`, `ODOO_WORKERS`), and MCP settings. `.env` is gitignored so secrets stay off Git.
- **`odoo.conf`**: Direct Odoo configuration (`http_interface`, `http_port`, `addons_path`, `data_dir`, `list_db`, and local DB connection defaults) for running `odoo-bin` manually. `scripts/odoo_ctl.py` also generates `data/odoo.runtime.conf` with auto-discovered `addons/` and `.env` overrides for upgrades and production.
- **`docker-compose.yml`**: Standalone shared PostgreSQL 16 container (`shared-postgres` on `localhost:5432` and Docker network `shared-db-network`), independent of Odoo and usable by any project on the device.
- **`addons/custom_erp/`**: Backend D2C Apparel & Phase-1 stack (`sale_management`, `sale_stock_margin`, `purchase`, `stock_dropshipping`, Indian GST `l10n_in*`, `payment_razorpay`, `crm`, `im_livechat`, `mass_mailing`, `website_blog`), Day-1 category tree & size/color/fabric attributes, Indian 5%/18% GST slab advisory, and COD verification / RTO tracking queues.
- **`addons/custom_store/`**: Version-controlled Website & eCommerce theme, exported homepage/header/footer/colors, `/shop` public categories, trust pages (`/size-guide`, `/shipping-policy`, `/return-policy`), and product/cart storefront hooks.
- **`deploy/` & `docker-compose.prod.yml`**: Production Docker stack (PostgreSQL 16 + Python 3.12 multi-worker Odoo + Nginx reverse proxy + cron backups + upgrade script).
- **`scripts/odoo_ctl.py`**: Backup, restore, and upgrade controller powering `save_db.bat`, `load_db.bat`, and `upgrade.bat`.
- **`docs/`**: Scaling roadmap (`SCALING_ROADMAP.md`) and local notes.
- **`odoo/`**, **`.venv/`**, **`data/`**, **`backups/`**: Local core clone, virtualenv, runtime data, and DB snapshots (gitignored).

---

## 🚀 Common Commands (Windows Dev)

- **Start Shared PostgreSQL (manual, independent of Odoo)**:
  ```bat
  docker compose up -d
  ```
- **Start Odoo Server (manual)**:
  ```bat
  .\.venv\Scripts\python.exe odoo\odoo-bin -c odoo.conf
  ```
  -> [http://localhost:8069](http://localhost:8069)
- **Safe Odoo Core Pull + Custom Addons Upgrade**:
  ```bat
  upgrade.bat
  ```
  *(Takes a pre-upgrade DB backup, verifies `odoo/` has no local edits, pulls latest upstream `20.0`, and runs `-u custom_erp,custom_store`.)*
- **Save / Restore DB Backup (for new environments / snapshots)**: `save_db.bat` / `load_db.bat`
- **Production Deployment**: See [`deploy/README.md`](deploy/README.md) and [`docker-compose.prod.yml`](docker-compose.prod.yml).
