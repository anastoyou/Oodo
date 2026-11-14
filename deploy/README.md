# Production Deployment Guide (Linux VPS + Docker + Nginx)

Follow these steps to take this exact repository into production without exposing local development credentials or touching `odoo/`.

## 1. Initial VPS Setup
1. Clone this repository and upstream Odoo `20.0` core:
   ```bash
   git clone <your-repo-url> /opt/odoo-app
   cd /opt/odoo-app
   git clone -b 20.0 --depth 1 https://github.com/odoo/odoo.git odoo
   ```
2. Create a secure `.env` from `.env.example` and replace **all** passwords:
   ```bash
   cp .env.example .env
   chmod 600 .env
   ```
   Set `ODOO_ENV=production`, `DB_HOST=db`, strong `DB_PASSWORD`, strong `ADMIN_PASSWORD`, and your production `ODOO_DB` name.
3. Build and start the stack:
   ```bash
   docker compose -f docker-compose.prod.yml build
   docker compose -f docker-compose.prod.yml up -d
   ```
4. Initialize a fresh production database (Country = India, without demo data) and install `custom_erp` + `custom_store`:
   ```bash
   docker compose -f docker-compose.prod.yml run --rm odoo -d yourbrand_prod -i custom_erp,custom_store --without-demo=all --stop-after-init --no-http
   ```
   Or restore a tested staging backup via `backups/`.

## 2. Pulling New Odoo Releases Without Breaking Custom Addons
- **Windows / Local Dev:** Run `upgrade.bat`
- **Linux Production VPS:**
  ```bash
  bash deploy/upgrade_prod.sh yourbrand_prod
  ```
Both workflows create a pre-upgrade DB+filestore backup, verify `odoo/` has zero local edits before running `git -C odoo pull --ff-only`, and run `-u custom_erp,custom_store` (plus any OCA addons added inside `addons/`).

## 3. Security Checklist Before Go-Live
- Put HTTPS (TLS via Certbot or Cloudflare) in front of port `80`/`443` in `deploy/nginx.conf`.
- Enable Odoo 2FA for all users and rotate any credentials from local dev before deploying.
- Schedule `deploy/backup_db.sh` via cron and copy `backups/` offsite (S3 / R2 / Backblaze / Google Drive).

