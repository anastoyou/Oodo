# Odoo 20.0 ERP (Direct Source Setup + `.env` Single Config)

This project runs **Odoo 20.0** directly from the GitHub source repository ([`odoo/odoo`](https://github.com/odoo/odoo)) in a Python `3.12` virtual environment (`.venv`), connected to a **PostgreSQL 16** container (`odoo-db`).

All database credentials, ports, and MCP settings live in **one single file: `.env`**.

---

## 📁 Project Layout

- **`.env`**: **Single source of truth** for DB connection (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`), Odoo server (`ADMIN_PASSWORD`, `ODOO_PORT`, `ODOO_BRANCH`), and MCP (`ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_PASSWORD`).
- **`odoo.conf`**: Structural Odoo paths and interface only (no DB host/user/password duplicated here). `start.bat` merges `.env` + `odoo.conf` into `data\odoo.runtime.conf` on launch.
- **`docker-compose.yml`**: Runs PostgreSQL 16 (`odoo-db`) using `DB_USER`, `DB_PASSWORD`, and `DB_PORT` from `.env`.
- **`scripts/odoo_ctl.py`**: Shared controller reading `.env` for all batch launchers.
- **`start.bat` / `stop.bat`**: Start or stop Odoo and PostgreSQL.
- **`save_db.bat` / `load_db.bat`**: Back up or restore any Odoo database + filestore `.zip` to/from `backups\`.
- **`reset-db.bat`**: Wipe the PostgreSQL volume and `data\filestore` + `data\sessions` to start fresh.
- **`addons/`**: Custom Odoo modules.
- **`docs/`**: Project notes and roadmaps.
- **`odoo/`**, **`.venv/`**, **`data/`**, **`backups/`**: Local source clone, virtualenv, runtime data, and backups (all gitignored).

---

## 🚀 Common Commands

- **Start Odoo**: Double-click `start.bat` (or pass Odoo flags like `start.bat -u all`). Open [http://localhost:8069](http://localhost:8069).
- **Stop Odoo & DB**: Run `stop.bat`.
- **Save DB backup**: Run `save_db.bat` (or `save_db.bat localhost`).
- **Restore DB backup**: Run `load_db.bat` (or `load_db.bat backups\<file>.zip localhost -y`).
- **Pull latest Odoo `20.0` updates**:
  ```powershell
  git -C e:\Code\Oodo\odoo pull --ff-only
  ```
