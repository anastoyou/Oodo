# Modules, Built-In Activation & Database Portability

> Companion to [`ARCHITECTURE_AND_CUSTOM_ERP.md`](./ARCHITECTURE_AND_CUSTOM_ERP.md) and [`OPERATIONS_GUIDE.md`](./OPERATIONS_GUIDE.md).

---

## 1. How Odoo Finds Modules (`addons_path`)

* Launching via `start.bat` or `upgrade.bat` runs [`scripts/odoo_ctl.py`](../scripts/odoo_ctl.py), which calls `discover_addons_paths()` and writes `data/odoo.runtime.conf` with:
  1. `odoo/addons/` (core Odoo)
  2. `addons/` (your custom modules)
  3. Any nested repository folders under `addons/` (such as OCA repos)
* In production, [`docker-compose.prod.yml`](../docker-compose.prod.yml) mounts both `./odoo:/opt/app/odoo:ro` and `./addons:/opt/app/addons:ro`, so production uses the exact same module discovery.

---

## 2. Activating a Built-In Module (e.g., `point_of_sale`, `hr_expense`)

All built-in Odoo Community modules **already exist on disk** inside `odoo/addons/` (for example, `odoo/addons/point_of_sale/`). Clicking **Activate** in **Apps** runs `button_immediate_install` → `_button_immediate_function` ([`ir_module.py`](../odoo/odoo/addons/base/models/ir_module.py)), which:

1. Marks the module and its `depends` in PostgreSQL (`ir.module.module`).
2. Rebuilds the live registry (`Registry.new(..., update_module=True)`), creating PostgreSQL tables and loading XML/CSV views, menus, security rules, and JS/CSS asset bundles into the database.
3. Marks the module `installed` and reloads your browser UI.

> **Important:** Clicking **Activate** updates the **database**, never the files in `odoo/`. If you later customize POS receipts or forms, put those customizations in `addons/custom_erp` or another module in `addons/`, and add the built-in module to `depends` if you want brand-new databases to auto-install it.

---

## 3. Adding or Updating Custom Modules in `addons/`

Putting a module folder in `addons/<my_module>/` only makes it discoverable on disk. Load it into PostgreSQL using one of these methods:

* **Install a new standalone custom module (CLI):**
  ```bat
  .\upgrade.bat --skip-pull --install --modules my_module
  .\start.bat
  ```
* **Or attach it as a dependency:** add `"my_module"` to `depends` in [`addons/custom_erp/__manifest__.py`](../addons/custom_erp/__manifest__.py) or [`addons/custom_store/__manifest__.py`](../addons/custom_store/__manifest__.py), then run `.\upgrade.bat --skip-pull` and `.\start.bat`.
* **Or install via UI:** restart with `start.bat`, enable Developer Mode, open **Apps → Update Apps List**, and click **Activate**.
* **After editing XML views, QWeb templates, or assets** inside `custom_store` or `custom_erp`, reload them into PostgreSQL:
  ```bat
  .\upgrade.bat --skip-pull
  .\start.bat
  ```

---

## 4. Using the Same Database in Another Project / Server

PostgreSQL stores **which modules are installed**, schema/tables, views, menus, and business data — **not** Python/JS/CSS source files and **not** uploaded images/attachments (`data/filestore/<db>/`).

| Scenario | Result when attaching this DB to another project |
| :--- | :--- |
| **Built-in modules** on the **same Odoo version (`20.0`)** | Works immediately — code is already in that project's `odoo/addons/`. |
| **Different Odoo major version** (e.g. `19.0` or `21.0`) | Cannot run directly; requires a major version migration (OpenUpgrade). |
| **Custom/OCA modules** (`custom_erp`, `custom_store`) **without** `addons/` | Fails / logs missing modules (`loading.py`) because PostgreSQL marks modules `installed` that aren't on disk in `addons_path`. |
| **Images, PDFs, compiled assets** | Missing unless `data/filestore/<db>/` is copied along with SQL. |

**Clean transfer checklist:** Match Odoo branch (`20.0`) + copy/deploy `addons/` + back up and restore SQL + filestore together using `.\save_db.bat` and `.\load_db.bat`.

