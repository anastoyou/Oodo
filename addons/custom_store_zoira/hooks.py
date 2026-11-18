from odoo import SUPERUSER_ID, api

STORE_SLUG = 'zoira'
STORE_NAME = 'ZOIRA LAWNS'
COMPANY_REF = 'ZOIRA LAWNS'
STORE_DOMAIN = 'http://zoira.localhost:8069'
MODULE_NAME = 'custom_store_zoira'


def _resolve_company(env):
    Company = env["res.company"].sudo()
    if COMPANY_REF:
        if COMPANY_REF.isdigit():
            comp = Company.browse(int(COMPANY_REF)).exists()
            if comp:
                return comp
        comp = Company.search([("name", "=ilike", COMPANY_REF)], limit=1)
        if comp:
            return comp
    return env.company


def _ensure_store_site_and_assets(env):
    Website = env["website"].sudo()
    site = Website.search([("x_store_code", "=", STORE_SLUG)], limit=1)
    if not site:
        site = Website.search([("name", "=ilike", STORE_NAME)], limit=1)
    company = _resolve_company(env)
    if not site:
        vals = {
            "name": STORE_NAME,
            "company_id": company.id,
            "x_store_code": STORE_SLUG,
        }
        if STORE_DOMAIN:
            vals["domain"] = STORE_DOMAIN
        site = Website.create(vals)
    else:
        updates = {}
        if not site.x_store_code:
            updates["x_store_code"] = STORE_SLUG
        if COMPANY_REF and site.company_id != company:
            updates["company_id"] = company.id
        if STORE_DOMAIN and not site.domain:
            updates["domain"] = STORE_DOMAIN
        if updates:
            site.write(updates)

    Asset = env["ir.asset"].sudo().with_context(active_test=False, no_cow=True)
    asset_specs = [
        {
            "name": f"{STORE_NAME} Primary Variables",
            "bundle": "web._assets_primary_variables",
            "directive": "before",
            "target": "website/static/src/scss/options/user_values.scss",
            "path": f"{MODULE_NAME}/static/src/scss/primary_variables.scss",
        },
        {
            "name": f"{STORE_NAME} Frontend SCSS",
            "bundle": "web.assets_frontend",
            "directive": "append",
            "target": False,
            "path": f"{MODULE_NAME}/static/src/scss/{STORE_SLUG}.scss",
        },
        {
            "name": f"{STORE_NAME} Frontend JS",
            "bundle": "web.assets_frontend",
            "directive": "append",
            "target": False,
            "path": f"{MODULE_NAME}/static/src/js/{STORE_SLUG}.js",
        },
    ]
    for spec in asset_specs:
        existing = Asset.search([
            ("website_id", "=", site.id),
            ("path", "=", spec["path"]),
        ], limit=1)
        if not existing:
            Asset.create({**spec, "website_id": site.id, "active": True})

    site._apply_store_homepage_template(f"{MODULE_NAME}.homepage_tmpl", force=False)
    site._apply_store_footer_template(f"{MODULE_NAME}.footer_tmpl", force=False)


def post_init_hook(env):
    _ensure_store_site_and_assets(env)
