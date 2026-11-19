"""Interactive CLI to scaffold, build, sync, and remove per-(website, product) custom PDPs."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import odoo_ctl  # noqa: E402

FRONTEND_DIR = ROOT / "frontend_pdp"
DEFAULT_REACT_TEMPLATE = FRONTEND_DIR / "src" / "DefaultPdpTemplate.tsx"
DEFAULT_REACT_FULL_DATA_TEMPLATE = FRONTEND_DIR / "src" / "DefaultPdpFullDataTemplate.tsx"


def slugify(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (raw or "").strip().lower()).strip("_")
    return cleaned or "product"


def extract_localized_text(raw_val) -> str:
    if isinstance(raw_val, dict):
        return raw_val.get("en_US") or next(iter(raw_val.values()), "") or ""
    return str(raw_val or "")


def resolve_addon_for_store_code(store_code: str | None) -> tuple[str, Path]:
    code = (store_code or "").strip().lower()
    if not code or code == "custom_store":
        addon_name = "custom_store"
    elif code.startswith("custom_store_"):
        addon_name = code
    else:
        addon_name = f"custom_store_{code}"
    return addon_name, ROOT / "addons" / addon_name


def _get_runtime_conf(cfg: dict[str, str]) -> Path:
    runtime_conf = ROOT / "data" / "odoo.runtime.conf"
    if runtime_conf.is_file():
        return runtime_conf
    base_conf = ROOT / "odoo.conf"
    if base_conf.is_file():
        return base_conf
    raise FileNotFoundError("Neither data/odoo.runtime.conf nor odoo.conf was found.")


def _run_odoo_shell(cfg: dict[str, str], db_name: str, python_code: str) -> str:
    odoo_bin = ROOT / "odoo" / "odoo-bin"
    conf_path = _get_runtime_conf(cfg)
    cmd = [
        sys.executable,
        str(odoo_bin),
        "shell",
        "-c",
        str(conf_path),
        "-d",
        db_name,
        "--no-http",
    ]
    proc = subprocess.run(
        cmd,
        input=python_code,
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"odoo-bin shell failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
        )
    return proc.stdout


def _fetch_websites(cfg: dict[str, str], db_name: str) -> list[dict]:
    with odoo_ctl.connect_pg(cfg, db_name) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT w.id, w.name, COALESCE(w.x_store_code, ''), w.domain, c.name
            FROM website w
            LEFT JOIN res_company c ON w.company_id = c.id
            ORDER BY w.id
            """
        )
        rows = cur.fetchall()
    result = []
    for wid, name, store_code, domain, company_name in rows:
        addon_name, addon_dir = resolve_addon_for_store_code(store_code)
        result.append(
            {
                "id": wid,
                "name": name,
                "store_code": store_code or "custom_store",
                "domain": domain or "",
                "company_name": company_name or "",
                "addon_name": addon_name,
                "addon_dir": addon_dir,
            }
        )
    return result


def _fetch_products(
    cfg: dict[str, str],
    db_name: str,
    website_id: int,
    search: str = "",
) -> list[dict]:
    with odoo_ctl.connect_pg(cfg, db_name) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT pt.id, pt.name, COALESCE(pt.default_code, ''), COALESCE(pt.is_published, false), pt.website_id
            FROM product_template pt
            WHERE pt.active = true
              AND (pt.website_id IS NULL OR pt.website_id = %s)
            ORDER BY pt.id
            """,
            (website_id,),
        )
        rows = cur.fetchall()

    term = search.strip().lower()
    products = []
    for pid, raw_name, default_code, is_published, prod_website_id in rows:
        name = extract_localized_text(raw_name)
        if term and term not in name.lower() and term not in default_code.lower() and term != str(pid):
            continue
        products.append(
            {
                "id": pid,
                "name": name,
                "default_code": default_code,
                "is_published": bool(is_published),
                "website_id": prod_website_id,
            }
        )
    return products


def _choose_website(websites: list[dict], requested: str | None) -> dict:
    if not websites:
        raise RuntimeError("No websites found in database.")
    if requested:
        q = requested.strip().lower()
        for site in websites:
            if (
                str(site["id"]) == q
                or site["store_code"].lower() == q
                or site["addon_name"].lower() == q
                or site["name"].lower() == q
            ):
                return site
        raise ValueError(f"Website {requested!r} not found.")

    print("\n=== Step 1: Choose Website ===")
    for idx, site in enumerate(websites, start=1):
        status = "OK" if site["addon_dir"].is_dir() else "MISSING ADDON"
        print(
            f"  [{idx}] {site['name']} (id={site['id']}, code={site['store_code']}, "
            f"company={site['company_name']}, addon={site['addon_name']} [{status}])"
        )
    while True:
        choice = input(f"Select website [1-{len(websites)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(websites):
            return websites[int(choice) - 1]
        for site in websites:
            if choice.lower() in (site["name"].lower(), site["store_code"].lower(), site["addon_name"].lower()):
                return site
        print("Invalid selection. Enter the number or store code.")


def _choose_product(
    cfg: dict[str, str],
    db_name: str,
    website: dict,
    requested: str | None,
) -> dict:
    all_products = _fetch_products(cfg, db_name, website["id"])
    if not all_products:
        raise RuntimeError(f"No active products found for website {website['name']!r}.")

    if requested:
        q = requested.strip().lower()
        for prod in all_products:
            if (
                str(prod["id"]) == q
                or (prod["default_code"] and prod["default_code"].lower() == q)
                or prod["name"].lower() == q
            ):
                return prod
        matches = [p for p in all_products if q in p["name"].lower() or q in p["default_code"].lower()]
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f"Product {requested!r} not found (or ambiguous).")

    print(f"\n=== Step 2: Choose Product for {website['name']} ===")
    filtered = all_products
    while True:
        display = filtered[:30]
        for idx, prod in enumerate(display, start=1):
            sku = f" [{prod['default_code']}]" if prod["default_code"] else ""
            pub = "Published" if prod["is_published"] else "Draft"
            print(f"  [{idx}] (ID {prod['id']}){sku} {prod['name']} ({pub})")
        if len(filtered) > 30:
            print(f"  ... showing 30 of {len(filtered)} products. Type /<search> to filter.")

        raw = input("Enter number, product ID, or '/keyword' to filter: ").strip()
        if raw.startswith("/"):
            filtered = _fetch_products(cfg, db_name, website["id"], search=raw[1:])
            if not filtered:
                print("No matching products; showing full list again.")
                filtered = all_products
            continue
        if raw.isdigit():
            num = int(raw)
            if 1 <= num <= len(display):
                return display[num - 1]
            for prod in all_products:
                if prod["id"] == num:
                    return prod
        for prod in all_products:
            if raw.lower() in (prod["name"].lower(), prod["default_code"].lower()):
                return prod
        print("Invalid selection.")


def _choose_code_type(requested: str | None) -> str:
    if requested:
        norm = requested.strip().lower()
        if norm in ("1", "native", "page_builder", "qweb"):
            return "native"
        if norm in ("2", "react", "tailwind", "react_tailwind"):
            return "react"
        raise ValueError(f"Invalid code type {requested!r}. Choose 'native' or 'react'.")

    print("\n=== Step 3: Choose PDP Code Type ===")
    print("  [1] Native with Page Builder (Odoo QWeb XML + Website Builder editable)")
    print("  [2] React + Tailwind CSS (TypeScript PdpPage.tsx + pdppage_full_data.tsx)")
    while True:
        raw = input("Select code type [1-2]: ").strip().lower()
        if raw in ("1", "native"):
            return "native"
        if raw in ("2", "react"):
            return "react"
        print("Invalid choice. Enter 1 (native) or 2 (react).")


def _build_native_xml(template_key: str, product_name: str, website_name: str) -> str:
    esc_product = escape(product_name)
    esc_site = escape(website_name)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="{template_key.split('.', 1)[1]}" name="{esc_product} Custom PDP ({esc_site})" track="1">
        <t t-set="navClass" t-valuef="light"/>
        <t t-set="is_fullwidth_content" t-value="website.product_page_image_width in ['none', '100_pc']"/>
        <t t-set="is_50_pc" t-value="website.product_page_image_width == '50_pc'"/>

        <t t-call="website.layout" additional_title="product.name">
            <div
                id="wrap"
                class="o_wsale_product_page oe_structure"
                t-att-data-has-available-uoms="has_available_uoms"
                t-att-data-name="product.name"
            >
                <section
                    id="product_detail"
                    data-anchor="true"
                    t-attf-class="oe_website_sale container py-4 #{{'discount' if combination_info['has_discounted_price'] else ''}}"
                    t-att-data-view-track="view_track and '1' or '0'"
                    t-att-data-name="combination_info['display_name']"
                >
                    <nav aria-label="breadcrumb" class="mb-3">
                        <ol class="o_wsale_breadcrumb breadcrumb m-0 p-0">
                            <li class="breadcrumb-item">
                                <a t-att-href="keep(shop_path)">Shop</a>
                            </li>
                            <t t-foreach="category.parents_and_self" t-as="cat">
                                <li class="breadcrumb-item">
                                    <a t-att-href="keep(cat.website_url)"><t t-out="cat.name"/></a>
                                </li>
                            </t>
                            <li class="breadcrumb-item active">
                                <span t-field="product.name"/>
                            </li>
                        </ol>
                    </nav>

                    <div
                        t-attf-class="row g-4 align-items-lg-start #{{website.product_page_cols_order == 'inverse' and 'flex-lg-row-reverse' or ''}}"
                        id="product_detail_main"
                        data-name="Product Page"
                        t-att-data-image-layout="website.product_page_image_layout"
                    >
                        <div
                            t-attf-class="o_wsale_product_images col-lg-7 o_wsale_sticky_object"
                            t-att-data-image-amount="len(product_variant._get_images() if product_variant else product._get_images())"
                            t-att-data-product-variant-id="product_variant.id"
                        >
                            <t t-call="website_sale.shop_product_images"/>
                        </div>

                        <div id="product_details" class="col-lg-5 position-relative position-lg-sticky o_wsale_sticky_object">
                            <div id="o_wsale_product_details_content" class="js_product o_wsale_content_contained">
                                <t t-set="is_add_to_cart_possible" t-value="product._has_ecommerce_sellable_variants()"/>
                                <t t-if="not is_add_to_cart_possible" t-call="website_sale.product_title"/>

                                <article t-if="is_add_to_cart_possible">
                                    <t t-call="website_sale.product_title"/>
                                    <div class="o_wsale_product_details_content_section o_wsale_product_details_content_section_price mb-4">
                                        <t t-call="website_sale.product_price"/>
                                    </div>
                                    <t name="variant_info">
                                        <div t-attf-class="o_wsale_product_details_content_section o_wsale_product_details_content_section_attributes mb-4 #{{not (product.valid_product_template_attribute_line_ids or (product_variant and product_variant._has_multiple_uoms())) and 'd-none' or ''}}">
                                            <t t-call="website_sale.variants" ul_class.f="flex-column" combination="combination_info['combination']"/>
                                        </div>
                                    </t>
                                    <div id="o_wsale_product_cta_section" class="o_wsale_product_details_content_section o_wsale_product_details_content_section_cta mb-4">
                                        <t t-call="website_sale.cta_wrapper"/>
                                    </div>
                                </article>
                            </div>
                        </div>
                    </div>
                </section>

                <!-- Editable Page Builder Section for {esc_product} -->
                <section class="s_text_block o_cc o_cc1 pt32 pb32 o_colored_level" data-snippet="s_text_block" data-name="Custom Story">
                    <div class="container s_allow_columns">
                        <div class="row">
                            <div class="col-lg-12">
                                <h3>Product Highlights</h3>
                                <p>Edit this section directly in Website Builder or in your custom_pdp XML file.</p>
                            </div>
                        </div>
                    </div>
                </section>

                <div id="product_full_description" t-field="product.website_description" class="oe_structure oe_empty mt16"/>
            </div>
        </t>
    </template>
</odoo>
'''


def _extract_native_template_inner_arch(xml_text: str, template_key: str) -> str:
    root = etree.fromstring(xml_text.encode("utf-8"))
    tmpl = root.find(".//template")
    if tmpl is None:
        raise ValueError("Expected a <template> element inside native PDP XML file.")
    tmpl.tag = "t"
    tmpl.set("t-name", template_key)
    tmpl.attrib.pop("id", None)
    tmpl.attrib.pop("name", None)
    tmpl.attrib.pop("track", None)
    return etree.tostring(tmpl, encoding="unicode")


def _run_npm_build(target: str | None = None, watch: bool = False) -> None:
    if not (FRONTEND_DIR / "node_modules").is_dir():
        print("[new_pdp] Installing frontend_pdp npm dependencies...")
        subprocess.run(["npm.cmd", "install"], cwd=str(FRONTEND_DIR), check=True)

    cmd = ["npm.cmd", "run", "watch" if watch else "build"]
    extra_args = []
    if target:
        extra_args.extend(["--target", target])
    if extra_args:
        cmd.append("--")
        cmd.extend(extra_args)

    subprocess.run(cmd, cwd=str(FRONTEND_DIR), check=True)


def _register_in_odoo(
    cfg: dict[str, str],
    db_name: str,
    *,
    website_id: int,
    product_id: int,
    addon_name: str,
    folder_name: str,
    mode: str,
    template_key: str | None = None,
    xml_arch: str | None = None,
    bundle_js: str | None = None,
    bundle_css: str | None = None,
    bundle_full_js: str | None = None,
    bundle_full_css: str | None = None,
    preserve_active: bool = False,
) -> None:
    payload = json.dumps(
        {
            "website_id": website_id,
            "product_tmpl_id": product_id,
            "addon_name": addon_name,
            "folder_name": folder_name,
            "mode": mode,
            "template_key": template_key,
            "xml_arch": xml_arch,
            "bundle_js": bundle_js,
            "bundle_css": bundle_css,
            "bundle_full_js": bundle_full_js,
            "bundle_full_css": bundle_full_css,
            "preserve_active": preserve_active,
        }
    )
    script = f"""
import json
data = json.loads({payload!r})
env['custom.store.product.pdp'].register_pdp(**data)
env.cr.commit()
print("REGISTERED_PDP_OK")
"""
    out = _run_odoo_shell(cfg, db_name, script)
    if "REGISTERED_PDP_OK" not in out:
        raise RuntimeError(f"Failed registering PDP in Odoo:\n{out}")


def _scaffold_and_register(
    cfg: dict[str, str],
    db_name: str,
    site: dict,
    product: dict,
    code_type: str,
    force: bool = False,
) -> None:
    addon_name = site["addon_name"]
    addon_dir = site["addon_dir"]
    if not addon_dir.is_dir():
        raise FileNotFoundError(
            f"Store addon directory not found: {addon_dir}. Create it first with new_store.bat."
        )

    folder_name = f"{product['id']}_{slugify(product['name'])}"
    pdp_dir = addon_dir / "custom_pdp" / folder_name
    pdp_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "website_id": site["id"],
        "website_name": site["name"],
        "store_code": site["store_code"],
        "addon_name": addon_name,
        "product_id": product["id"],
        "product_name": product["name"],
        "folder_name": folder_name,
        "mode": code_type,
    }

    if code_type == "native":
        native_dir = pdp_dir / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        xml_file = native_dir / f"pdp_{folder_name}.xml"
        template_key = f"{addon_name}.pdp_{folder_name}"
        if not xml_file.exists() or force:
            xml_text = _build_native_xml(template_key, product["name"], site["name"])
            xml_file.write_text(xml_text, encoding="utf-8")
        else:
            xml_text = xml_file.read_text(encoding="utf-8")
        meta["template_key"] = template_key
        meta["native_file"] = str(xml_file.relative_to(ROOT))
        (pdp_dir / "pdp.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        xml_arch = _extract_native_template_inner_arch(xml_text, template_key)
        _register_in_odoo(
            cfg,
            db_name,
            website_id=site["id"],
            product_id=product["id"],
            addon_name=addon_name,
            folder_name=folder_name,
            mode="native",
            template_key=template_key,
            xml_arch=xml_arch,
        )
        print(f"\n[OK] Native PDP created & registered:")
        print(f"     Folder : {pdp_dir}")
        print(f"     XML    : {xml_file}")
    else:
        if not DEFAULT_REACT_TEMPLATE.is_file():
            raise FileNotFoundError(f"Starter template missing: {DEFAULT_REACT_TEMPLATE}")
        if not DEFAULT_REACT_FULL_DATA_TEMPLATE.is_file():
            raise FileNotFoundError(f"Starter full-data template missing: {DEFAULT_REACT_FULL_DATA_TEMPLATE}")
        react_dir = pdp_dir / "react"
        react_dir.mkdir(parents=True, exist_ok=True)
        tsx_file = react_dir / "PdpPage.tsx"
        legacy_jsx = react_dir / "PdpPage.jsx"
        full_data_file = react_dir / "pdppage_full_data.tsx"
        css_file = react_dir / "pdp.css"

        if force or (not tsx_file.exists() and not legacy_jsx.is_file()):
            tsx_file.write_text(DEFAULT_REACT_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
            if legacy_jsx.is_file():
                legacy_jsx.unlink()
        elif legacy_jsx.is_file() and not tsx_file.is_file():
            jsx_src = legacy_jsx.read_text(encoding="utf-8")
            if "PdpPageProps" not in jsx_src:
                jsx_src = jsx_src.replace(
                    "export default function PdpPage({ bootstrap })",
                    'import type { PdpPageProps } from "@odoo-pdp/types";\n\nexport default function PdpPage({ bootstrap }: PdpPageProps)',
                )
            tsx_file.write_text(jsx_src, encoding="utf-8")
            legacy_jsx.unlink()

        if not full_data_file.exists() or force:
            full_data_file.write_text(
                DEFAULT_REACT_FULL_DATA_TEMPLATE.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        if not css_file.exists() or force:
            css_file.write_text(
                "/* Add optional per-product CSS scoped under #custom-react-pdp-root */\n",
                encoding="utf-8",
            )

        _run_npm_build(target=f"{addon_name}/{folder_name}")
        dist_dir = addon_dir / "static" / "dist" / f"pdp_{folder_name}"
        bundle_js = f"/{addon_name}/static/dist/pdp_{folder_name}/pdp.js"
        bundle_css = (
            f"/{addon_name}/static/dist/pdp_{folder_name}/pdp.css"
            if (dist_dir / "pdp.css").is_file()
            else ""
        )
        bundle_full_js = (
            f"/{addon_name}/static/dist/pdp_{folder_name}/pdp_full_data.js"
            if (dist_dir / "pdp_full_data.js").is_file()
            else ""
        )
        bundle_full_css = (
            f"/{addon_name}/static/dist/pdp_{folder_name}/pdp_full_data.css"
            if (dist_dir / "pdp_full_data.css").is_file()
            else ""
        )
        meta["react_entry"] = str(tsx_file.relative_to(ROOT))
        meta["react_full_data"] = str(full_data_file.relative_to(ROOT))
        meta["bundle_js"] = bundle_js
        meta["bundle_css"] = bundle_css
        meta["bundle_full_js"] = bundle_full_js
        meta["bundle_full_css"] = bundle_full_css
        (pdp_dir / "pdp.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        _register_in_odoo(
            cfg,
            db_name,
            website_id=site["id"],
            product_id=product["id"],
            addon_name=addon_name,
            folder_name=folder_name,
            mode="react",
            bundle_js=bundle_js,
            bundle_css=bundle_css,
            bundle_full_js=bundle_full_js,
            bundle_full_css=bundle_full_css,
        )
        print(f"\n[OK] React + Tailwind (TypeScript) PDP created, built & registered:")
        print(f"     Folder   : {pdp_dir}")
        print(f"     Customer : {tsx_file}")
        print(f"     Dev Ref  : {full_data_file}")
        print(f"     Bundle   : {dist_dir}")
        print(f"     Watch    : .\\new_pdp.bat --watch --target {addon_name}/{folder_name}")

    port = int(cfg.get("ODOO_PORT", "8069"))
    domain = site["domain"] or f"http://localhost:{port}"
    print(f"     URL      : {domain.rstrip('/')}/shop/{product['id']}")
    if code_type == "react":
        print(f"     Dev URL  : {domain.rstrip('/')}/shop/{product['id']}?pdp_dev=full  (editors/admin only)")
    if not product.get("is_published"):
        print("     Note     : This product is currently Draft/Unpublished; publish it or sign in to preview.")
    if code_type == "native" and odoo_ctl.is_port_open("127.0.0.1", port):
        print("     Note     : If Odoo is already running, restart/reload if QWeb cache holds an older view.")


def _sync_existing_pdp(cfg: dict[str, str], db_name: str, target_filter: str | None = None) -> None:
    synced = 0
    for addon_dir in sorted((ROOT / "addons").glob("custom_store*")):
        pdp_root = addon_dir / "custom_pdp"
        if not pdp_root.is_dir():
            continue
        for pdp_dir in sorted(pdp_root.iterdir()):
            meta_file = pdp_dir / "pdp.json"
            if not meta_file.is_file():
                continue
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            key = f"{meta['addon_name']}/{meta['folder_name']}"
            if target_filter and target_filter not in (key, meta["folder_name"]):
                continue
            if meta["mode"] == "native":
                xml_file = pdp_dir / "native" / f"pdp_{meta['folder_name']}.xml"
                xml_arch = _extract_native_template_inner_arch(
                    xml_file.read_text(encoding="utf-8"),
                    meta["template_key"],
                )
                _register_in_odoo(
                    cfg,
                    db_name,
                    website_id=int(meta["website_id"]),
                    product_id=int(meta["product_id"]),
                    addon_name=meta["addon_name"],
                    folder_name=meta["folder_name"],
                    mode="native",
                    template_key=meta["template_key"],
                    xml_arch=xml_arch,
                    preserve_active=True,
                )
            else:
                react_dir = pdp_dir / "react"
                tsx_file = react_dir / "PdpPage.tsx"
                legacy_jsx = react_dir / "PdpPage.jsx"
                if legacy_jsx.is_file() and not tsx_file.is_file():
                    jsx_src = legacy_jsx.read_text(encoding="utf-8")
                    if "PdpPageProps" not in jsx_src:
                        jsx_src = jsx_src.replace(
                            "export default function PdpPage({ bootstrap })",
                            'import type { PdpPageProps } from "@odoo-pdp/types";\n\nexport default function PdpPage({ bootstrap }: PdpPageProps)',
                        )
                    tsx_file.write_text(jsx_src, encoding="utf-8")
                    legacy_jsx.unlink()
                full_data_file = react_dir / "pdppage_full_data.tsx"
                if DEFAULT_REACT_FULL_DATA_TEMPLATE.is_file() and not full_data_file.is_file():
                    full_data_file.write_text(
                        DEFAULT_REACT_FULL_DATA_TEMPLATE.read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )
                _run_npm_build(target=key)
                dist_dir = addon_dir / "static" / "dist" / f"pdp_{meta['folder_name']}"
                bundle_js = f"/{meta['addon_name']}/static/dist/pdp_{meta['folder_name']}/pdp.js"
                bundle_css = (
                    f"/{meta['addon_name']}/static/dist/pdp_{meta['folder_name']}/pdp.css"
                    if (dist_dir / "pdp.css").is_file()
                    else ""
                )
                bundle_full_js = (
                    f"/{meta['addon_name']}/static/dist/pdp_{meta['folder_name']}/pdp_full_data.js"
                    if (dist_dir / "pdp_full_data.js").is_file()
                    else ""
                )
                bundle_full_css = (
                    f"/{meta['addon_name']}/static/dist/pdp_{meta['folder_name']}/pdp_full_data.css"
                    if (dist_dir / "pdp_full_data.css").is_file()
                    else ""
                )
                meta["react_entry"] = str(tsx_file.relative_to(ROOT))
                meta["react_full_data"] = str(full_data_file.relative_to(ROOT))
                meta["bundle_js"] = bundle_js
                meta["bundle_css"] = bundle_css
                meta["bundle_full_js"] = bundle_full_js
                meta["bundle_full_css"] = bundle_full_css
                meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                _register_in_odoo(
                    cfg,
                    db_name,
                    website_id=int(meta["website_id"]),
                    product_id=int(meta["product_id"]),
                    addon_name=meta["addon_name"],
                    folder_name=meta["folder_name"],
                    mode="react",
                    bundle_js=bundle_js,
                    bundle_css=bundle_css,
                    bundle_full_js=bundle_full_js,
                    bundle_full_css=bundle_full_css,
                    preserve_active=True,
                )
            print(f"[sync] Synced {key} ({meta['mode']})")
            synced += 1
    if not synced:
        print("[sync] No matching custom PDPs found.")


def _pull_native_pdp(cfg: dict[str, str], db_name: str, target_filter: str | None = None) -> None:
    with odoo_ctl.connect_pg(cfg, db_name) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.addon_name, p.folder_name, p.template_key, v.arch_db
            FROM custom_store_product_pdp p
            JOIN ir_ui_view v ON v.id = p.view_id
            WHERE p.mode = 'native' AND p.active = true
            ORDER BY p.id
            """
        )
        rows = cur.fetchall()
    pulled = 0
    for addon_name, folder_name, template_key, raw_arch in rows:
        key = f"{addon_name}/{folder_name}"
        if target_filter and target_filter not in (key, folder_name):
            continue
        arch = extract_localized_text(raw_arch)
        if not arch:
            continue
        root = etree.fromstring(arch.encode("utf-8"))
        root.tag = "template"
        root.set("id", template_key.split(".", 1)[1])
        root.attrib.pop("t-name", None)
        tmpl_xml = etree.tostring(root, encoding="unicode")
        xml_file = ROOT / "addons" / addon_name / "custom_pdp" / folder_name / "native" / f"pdp_{folder_name}.xml"
        xml_file.parent.mkdir(parents=True, exist_ok=True)
        xml_file.write_text(
            f'<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n{tmpl_xml}\n</odoo>\n',
            encoding="utf-8",
        )
        print(f"[pull] Pulled DB view -> {xml_file}")
        pulled += 1
    if not pulled:
        print("[pull] No matching native PDPs found in database.")


def _remove_pdp(cfg: dict[str, str], db_name: str, website_id: int, product_id: int) -> None:
    script = f"""
recs = env['custom.store.product.pdp'].sudo().with_context(active_test=False).search([
    ('website_id', '=', {website_id}),
    ('product_tmpl_id', '=', {product_id}),
])
count = len(recs)
if recs:
    recs.unlink()
env.cr.commit()
print(f"REMOVED_COUNT={{count}}")
"""
    out = _run_odoo_shell(cfg, db_name, script)
    print(out.strip())


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage per-(website, product) custom PDPs.")
    parser.add_argument("--website", help="Website ID, store code (e.g. fairtag), or name.")
    parser.add_argument("--product", help="Product Template ID, SKU, or name.")
    parser.add_argument("--type", choices=["native", "react"], help="PDP code type.")
    parser.add_argument("--database", help="Target Odoo database (defaults to .env ODOO_DB).")
    parser.add_argument("--force", action="store_true", help="Overwrite existing scaffold files.")
    parser.add_argument("--build", action="store_true", help="Build React+Tailwind PDP bundle(s).")
    parser.add_argument("--watch", action="store_true", help="Watch React+Tailwind PDP bundle(s).")
    parser.add_argument("--target", help="Optional target '<addon>/<folder>' or '<folder>' for build/watch/sync/pull.")
    parser.add_argument("--sync", action="store_true", help="Push disk PDP files/bundles to DB.")
    parser.add_argument("--pull", action="store_true", help="Pull Website Builder edits from DB into native XML.")
    parser.add_argument("--remove", action="store_true", help="Remove PDP mapping, view, and disk folder.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if args.build or args.watch:
        _run_npm_build(target=args.target, watch=args.watch)
        return 0

    cfg = odoo_ctl.load_env(ROOT)
    db_name = args.database or cfg["ODOO_DB"]
    odoo_ctl.ensure_postgres(ROOT, cfg)

    if args.sync:
        _sync_existing_pdp(cfg, db_name, target_filter=args.target)
        return 0

    if args.pull:
        _pull_native_pdp(cfg, db_name, target_filter=args.target)
        return 0

    websites = _fetch_websites(cfg, db_name)
    site = _choose_website(websites, args.website)
    product = _choose_product(cfg, db_name, site, args.product)

    if args.remove:
        _remove_pdp(cfg, db_name, site["id"], product["id"])
        return 0

    code_type = _choose_code_type(args.type)
    _scaffold_and_register(cfg, db_name, site, product, code_type, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
