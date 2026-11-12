# Odoo ERP with Local PostgreSQL (High-Performance Setup)

This configuration runs **Odoo ERP** with a high-performance **Local PostgreSQL 16** database container running directly inside Docker. 

Because both containers run on the same Docker bridge network on your computer, database query latency is **< 0.5 ms**, making Odoo blazing fast.

---

## 📁 File Structure

- **`docker-compose.yml`**: Docker Compose definition running both `odoo` and local `db` (Postgres 16).
- **`.env`**: Local database credentials and port settings.
- **`config/odoo.conf`**: Odoo configuration pointing to the local `db` container.
- **`addons/`**: Directory for custom modules.
- **`start.bat`**: Windows batch script to start both Odoo and PostgreSQL with one click.
- **`stop.bat`**: Windows batch script to cleanly stop the containers.
- **`reset-db.bat`**: Windows batch script to wipe the database and filestore completely to start fresh.

---

## 🚀 How to Run

1. **Start Odoo & PostgreSQL**:
   * Double-click **`start.bat`** (or run `docker compose up -d`).

2. **Open in Browser**:
   * Go to **[http://localhost:8069](http://localhost:8069)**.
   * If creating a database, fill in:
     * **Master Password**: `masteradmin`
     * **Database Name**: e.g., `odoo` or `mycompany`
     * **Email**: `admin@gmail.com`
     * **Password**: `admin`
     * **Demo data**: optional (uncheck for a clean empty system)
   * Click **Create database** (takes ~5–10 seconds locally).
