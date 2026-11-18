"""Scaffold a new Website-Builder-compatible store addon under addons/custom_store_<slug>."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent


def normalize_slug(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", raw.strip().lower()).strip("_")
    if not slug or not slug[0].isalpha():
        raise ValueError(f"Invalid store slug {raw!r}: must start with a letter and contain a-z, 0-9, or _.")
    if slug == "custom_store":
        raise ValueError("Slug 'custom_store' is reserved for the base Website 1 addon.")
    return slug


def write_text(path: Path, content: str, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.write_text(content, encoding="utf-8")


def generate_store_addon(
    slug: str,
    name: str,
    company: str = "",
    domain: str = "",
    accent: str = "#1d4ed8",
    dark: str = "#0f172a",
    force: bool = False,
) -> Path:
    module_name = f"custom_store_{slug}"
    addon_dir = ROOT / "addons" / module_name
    if addon_dir.exists() and not force:
        raise FileExistsError(f"Addon folder already exists: {addon_dir} (pass --force to overwrite)")

    esc_name = escape(name)
    esc_company = escape(company)
    esc_domain = escape(domain)
    css_prefix = f"o_{slug}"
    palette_name = f"store-{slug.replace('_', '-')}"
    class_prefix = "".join(part.capitalize() for part in slug.split("_"))

    write_text(addon_dir / "__init__.py", "from .hooks import post_init_hook\n", force=force)

    write_text(
        addon_dir / "__manifest__.py",
        f'''{{
    "name": "{esc_name} Storefront",
    "version": "20.0.1.0.0",
    "category": "Website/eCommerce",
    "summary": "Isolated, Builder-compatible storefront for {esc_name} ({module_name}).",
    "author": "ZOEE GLOBAL PRIVATE LIMITED",
    "depends": [
        "custom_store",
    ],
    "data": [
        "views/header.xml",
        "views/homepage.xml",
        "views/footer.xml",
        "views/shop_templates.xml",
        "views/product_templates.xml",
        "views/cart_templates.xml",
        "views/checkout_templates.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}}
''',
        force=force,
    )

    write_text(
        addon_dir / "hooks.py",
        f'''from odoo import SUPERUSER_ID, api

STORE_SLUG = {slug!r}
STORE_NAME = {name!r}
COMPANY_REF = {company!r}
STORE_DOMAIN = {domain!r}
MODULE_NAME = {module_name!r}


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
        vals = {{
            "name": STORE_NAME,
            "company_id": company.id,
            "x_store_code": STORE_SLUG,
        }}
        if STORE_DOMAIN:
            vals["domain"] = STORE_DOMAIN
        site = Website.create(vals)
    else:
        updates = {{}}
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
        {{
            "name": f"{{STORE_NAME}} Primary Variables",
            "bundle": "web._assets_primary_variables",
            "directive": "before",
            "target": "website/static/src/scss/options/user_values.scss",
            "path": f"{{MODULE_NAME}}/static/src/scss/primary_variables.scss",
        }},
        {{
            "name": f"{{STORE_NAME}} Frontend SCSS",
            "bundle": "web.assets_frontend",
            "directive": "append",
            "target": False,
            "path": f"{{MODULE_NAME}}/static/src/scss/{{STORE_SLUG}}.scss",
        }},
        {{
            "name": f"{{STORE_NAME}} Frontend JS",
            "bundle": "web.assets_frontend",
            "directive": "append",
            "target": False,
            "path": f"{{MODULE_NAME}}/static/src/js/{{STORE_SLUG}}.js",
        }},
    ]
    for spec in asset_specs:
        existing = Asset.search([
            ("website_id", "=", site.id),
            ("path", "=", spec["path"]),
        ], limit=1)
        if not existing:
            Asset.create({{**spec, "website_id": site.id, "active": True}})

    site._apply_store_homepage_template(f"{{MODULE_NAME}}.homepage_tmpl", force=False)
    site._apply_store_footer_template(f"{{MODULE_NAME}}.footer_tmpl", force=False)


def post_init_hook(env):
    _ensure_store_site_and_assets(env)
''',
        force=force,
    )

    write_text(
        addon_dir / "views" / "header.xml",
        f'''<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="header_{slug}" inherit_id="website.layout" name="{esc_name} Header" priority="30">
        <xpath expr="//header[@id='top']" position="attributes">
            <attribute name="t-attf-class" add="#{{'{css_prefix}_header' if (website and website.x_store_code == '{slug}') else ''}}" separator=" "/>
        </xpath>
    </template>

    <template id="header_disclaimer_{slug}" inherit_id="website.option_header_disclaimer" name="{esc_name} Header Announcement" priority="25">
        <xpath expr="//div[hasclass('s_headline')]" position="before">
            <div t-if="website and website.x_store_code == '{slug}'" class="s_headline oe_no_drop_above o_colored_level o_cc o_cc5 pt4 pb4">
                <div class="text-center px-3">
                    <small>Welcome to {esc_name} &#183; Managed by ZOEE GLOBAL PRIVATE LIMITED</small>
                </div>
            </div>
        </xpath>
        <xpath expr="//div[hasclass('s_headline')][last()]" position="attributes">
            <attribute name="t-if">not (website and website.x_store_code == '{slug}')</attribute>
        </xpath>
    </template>
</odoo>
''',
        force=force,
    )

    write_text(
        addon_dir / "views" / "homepage.xml",
        f'''<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Builder-compatible starter Homepage seeded into {esc_name} on install (syncable with sync_store.bat) -->
    <template id="homepage_tmpl" name="{esc_name} Starter Homepage">
        <t t-call="website.layout" pageName.f="homepage">
            <div id="wrap" class="oe_structure">
                <section class="s_cover o_cc o_cc5 pt96 pb96 o_colored_level" data-snippet="s_cover" data-name="Hero Cover">
                    <div class="container s_allow_columns text-center">
                        <span class="badge text-bg-primary text-uppercase mb-3 px-3 py-2">{esc_name}</span>
                        <h1 class="display-3 fw-bold mb-3">{esc_name} Official Store</h1>
                        <p class="lead mb-4">
                            Discover curated products from {esc_name} &#8212; managed by ZOEE GLOBAL PRIVATE LIMITED.
                        </p>
                        <div class="d-flex justify-content-center gap-2 flex-wrap">
                            <a href="/shop" class="btn btn-primary btn-lg px-4 o_translate_inline">Shop Now</a>
                            <a href="/contactus" class="btn btn-outline-light btn-lg px-4 o_translate_inline">Contact Us</a>
                        </div>
                    </div>
                </section>

                <section class="s_three_columns o_cc o_cc1 pt48 pb48 o_colored_level" data-vcss="001" data-snippet="s_three_columns" data-name="Highlights">
                    <div class="container s_allow_columns">
                        <div class="row g-3">
                            <div class="col-md-4 pt8 pb8">
                                <div class="s_card {css_prefix}_card card h-100 o_cc o_cc2 p-4" data-vxml="001" data-snippet="s_card" data-name="Highlight Card">
                                    <h3 class="h5 card-title">Curated Catalog</h3>
                                    <p class="card-text small text-muted mb-0">Dedicated products, suppliers, and inventory scoped cleanly to {esc_name}.</p>
                                </div>
                            </div>
                            <div class="col-md-4 pt8 pb8">
                                <div class="s_card {css_prefix}_card card h-100 o_cc o_cc2 p-4" data-vxml="001" data-snippet="s_card" data-name="Highlight Card">
                                    <h3 class="h5 card-title">Fast Dispatch</h3>
                                    <p class="card-text small text-muted mb-0">Pan-India doorstep delivery with live order and portal tracking.</p>
                                </div>
                            </div>
                            <div class="col-md-4 pt8 pb8">
                                <div class="s_card {css_prefix}_card card h-100 o_cc o_cc2 p-4" data-vxml="001" data-snippet="s_card" data-name="Highlight Card">
                                    <h3 class="h5 card-title">Trusted Support</h3>
                                    <p class="card-text small text-muted mb-0">Backed by ZOEE GLOBAL PRIVATE LIMITED with GST-compliant billing.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
            </div>
        </t>
    </template>
</odoo>
''',
        force=force,
    )

    write_text(
        addon_dir / "views" / "footer.xml",
        f'''<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Builder-compatible starter Footer seeded into {esc_name} on install (syncable with sync_store.bat) -->
    <template id="footer_tmpl" name="{esc_name} Starter Footer">
        <div id="footer" class="oe_structure oe_structure_solo {css_prefix}_footer border text-break" t-ignore="true" t-if="not no_footer" style="--box-border-left-width: 0px; --box-border-right-width: 0px;">
            <section class="s_text_block pt40 pb24 o_colored_level" data-snippet="s_text_block" data-name="Footer Content">
                <div class="container">
                    <div class="row g-4">
                        <div class="col-lg-4 col-sm-6 pt16 pb16">
                            <h5>{esc_name}</h5>
                            <p class="small mb-0">
                                Official online storefront for {esc_name}, a brand managed by ZOEE GLOBAL PRIVATE LIMITED.
                            </p>
                        </div>
                        <div class="col-lg-4 col-sm-6 pt16 pb16">
                            <h5>Quick Links</h5>
                            <ul class="list-unstyled d-flex flex-column gap-1">
                                <li><a href="/">Home</a></li>
                                <li><a href="/shop">Shop</a></li>
                                <li><a href="/my">My Account</a></li>
                                <li><a href="/support">Support</a></li>
                            </ul>
                        </div>
                        <div class="col-lg-4 col-sm-6 pt16 pb16">
                            <h5>Contact</h5>
                            <ul class="list-unstyled d-flex flex-column gap-1 small">
                                <li><a href="/contactus">Contact Form</a></li>
                                <li><a href="/privacy">Privacy Policy</a></li>
                            </ul>
                        </div>
                    </div>
                </div>
            </section>
        </div>
    </template>
</odoo>
''',
        force=force,
    )

    write_text(
        addon_dir / "views" / "shop_templates.xml",
        f'''<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="shop_{slug}" inherit_id="website_sale.products" name="{esc_name} Shop Page">
        <xpath expr="//div[@id='wrap']" position="attributes">
            <attribute name="t-attf-class" add="#{{'{css_prefix}_shop' if (website and website.x_store_code == '{slug}') else ''}}" separator=" "/>
        </xpath>
        <xpath expr="//header[@id='o_wsale_products_header']" position="before">
            <div t-if="website and website.x_store_code == '{slug}'" class="{css_prefix}_shop_banner p-4 mb-4 rounded">
                <span class="badge text-bg-primary text-uppercase mb-2">{esc_name}</span>
                <h2 class="h4 text-white mb-1">{esc_name} Collection</h2>
                <p class="small text-white-50 mb-0">Curated items exclusively for {esc_name}.</p>
            </div>
        </xpath>
    </template>
</odoo>
''',
        force=force,
    )

    write_text(
        addon_dir / "views" / "product_templates.xml",
        f'''<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="product_{slug}" inherit_id="website_sale.product" name="{esc_name} Product Page">
        <xpath expr="//div[@id='wrap']" position="attributes">
            <attribute name="t-attf-class" add="#{{'{css_prefix}_product' if (website and website.x_store_code == '{slug}') else ''}}" separator=" "/>
        </xpath>
    </template>
</odoo>
''',
        force=force,
    )

    write_text(
        addon_dir / "views" / "cart_templates.xml",
        f'''<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="cart_{slug}" inherit_id="website_sale.cart" name="{esc_name} Cart Page">
        <xpath expr="//div[@id='shop_cart']" position="attributes">
            <attribute name="t-attf-class" add="#{{'{css_prefix}_cart' if (website and website.x_store_code == '{slug}') else ''}}" separator=" "/>
        </xpath>
    </template>
</odoo>
''',
        force=force,
    )

    write_text(
        addon_dir / "views" / "checkout_templates.xml",
        f'''<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="checkout_{slug}" inherit_id="website_sale.checkout_layout" name="{esc_name} Checkout Layout">
        <xpath expr="//div[@id='wrap']" position="attributes">
            <attribute name="t-attf-class" add="#{{'{css_prefix}_checkout' if (website and website.x_store_code == '{slug}') else ''}}" separator=" "/>
        </xpath>
    </template>
</odoo>
''',
        force=force,
    )

    write_text(
        addon_dir / "static" / "src" / "scss" / "primary_variables.scss",
        f'''// Isolated color palette for {esc_name} ({module_name})
$o-color-palettes: map-merge($o-color-palettes, (
    '{palette_name}': (
        'o-color-1': {accent},
        'o-color-2': {dark},
        'o-color-3': #F1F5F9,
        'o-color-4': #FFFFFF,
        'o-color-5': {dark},
        'o-cc5-headings': #FFFFFF,
        'o-cc5-link': #E2E8F0,
        'menu': 1,
        'footer': 5,
        'copyright': 5,
    ),
));

$o-gray-color-palettes: map-merge($o-gray-color-palettes, (
    '{palette_name}': map-get($o-gray-color-palettes, 'base-1'),
));

$o-theme-color-palettes: map-merge($o-theme-color-palettes, (
    '{palette_name}': map-get($o-theme-color-palettes, 'base-1'),
));

$o-selected-color-palettes-names: append($o-selected-color-palettes-names, '{palette_name}');

$o-user-website-values: map-merge((
    'color-palettes-name': '{palette_name}',
), $o-user-website-values);
''',
        force=force,
    )

    write_text(
        addon_dir / "static" / "src" / "scss" / f"{slug}.scss",
        f'''// Isolated frontend styles for {esc_name} ({module_name})
html[data-store-code="{slug}"] {{
    --store-accent: var(--primary, {accent});
    --store-dark: var(--secondary, {dark});

    .{css_prefix}_shop_banner {{
        background: linear-gradient(135deg, var(--store-dark) 0%, color-mix(in srgb, var(--store-dark) 80%, var(--store-accent)) 100%);
    }}

    .{css_prefix}_card {{
        transition: transform 0.2s ease, box-shadow 0.2s ease;

        &:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
        }}
    }}
}}
''',
        force=force,
    )

    write_text(
        addon_dir / "static" / "src" / "js" / f"{slug}.js",
        f'''/* @odoo-module */

import {{ Interaction }} from "@web/public/interaction";
import {{ registry }} from "@web/core/registry";

export class {class_prefix}Storefront extends Interaction {{
    static selector = "html[data-store-code='{slug}'] #wrapwrap";

    start() {{
        // Add {esc_name}-specific JS interactions here without affecting other websites.
    }}
}}

registry
    .category("public.interactions")
    .add("{module_name}.storefront", {class_prefix}Storefront);
''',
        force=force,
    )

    return addon_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a new isolated, Builder-compatible Odoo store addon.")
    parser.add_argument("slug", help="Short lowercase store code (e.g. fairtag, zoira)")
    parser.add_argument("name", help="Display website name (e.g. 'FAIRTAG')")
    parser.add_argument("--company", default="", help="Company name or ID to link (e.g. 'FAIRTAG')")
    parser.add_argument("--domain", default="", help="Optional website domain (e.g. 'http://fairtag.localhost:8069')")
    parser.add_argument("--accent", default="#1d4ed8", help="Primary hex color (default: #1d4ed8)")
    parser.add_argument("--dark", default="#0f172a", help="Dark hex color (default: #0f172a)")
    parser.add_argument("--force", action="store_true", help="Overwrite if addon directory exists")
    parser.add_argument("--install", action="store_true", help="Install the new addon into Odoo right away")
    args = parser.parse_args()

    slug = normalize_slug(args.slug)
    addon_dir = generate_store_addon(
        slug=slug,
        name=args.name,
        company=args.company,
        domain=args.domain,
        accent=args.accent,
        dark=args.dark,
        force=args.force,
    )
    print(f"Created store addon: {addon_dir}")

    if args.install:
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "odoo_ctl.py"),
            "upgrade",
            "--skip-pull",
            "--install",
            "--modules",
            addon_dir.name,
        ]
        print("Installing module via:", " ".join(cmd))
        return subprocess.call(cmd, cwd=str(ROOT))
    else:
        print(f"Next step: .\\upgrade.bat --skip-pull --install --modules {addon_dir.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
