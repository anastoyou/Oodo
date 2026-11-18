"""Sync Website Builder DB edits <-> addons/custom_store*/views/ XML files."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import odoo_ctl  # noqa: E402


def resolve_addon(slug: str) -> tuple[str, Path, str, str]:
    clean = slug.strip().lower()
    if clean == "custom_store":
        return "custom_store", ROOT / "addons" / "custom_store", "homepage_custom_tmpl", "footer_custom_tmpl"
    if clean.startswith("custom_store_"):
        code = clean[len("custom_store_"):]
        return clean, ROOT / "addons" / clean, "homepage_tmpl", "footer_tmpl"
    return f"custom_store_{clean}", ROOT / "addons" / f"custom_store_{clean}", "homepage_tmpl", "footer_tmpl"


def _extract_arch(raw_arch) -> str:
    if isinstance(raw_arch, dict):
        return raw_arch.get("en_US") or next(iter(raw_arch.values()), "")
    return raw_arch or ""


def pull_store(slug: str) -> int:
    module_name, addon_dir, hp_id, ft_id = resolve_addon(slug)
    if not addon_dir.is_dir():
        raise FileNotFoundError(f"Addon directory not found: {addon_dir}")

    store_code = "custom_store" if module_name == "custom_store" else module_name[len("custom_store_"):]
    cfg = odoo_ctl.load_env(ROOT)
    db_name = cfg["ODOO_DB"]

    with odoo_ctl.connect_pg(cfg, db_name) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name FROM website WHERE x_store_code = %s LIMIT 1", (store_code,))
        row = cur.fetchone()
        if not row and store_code == "custom_store":
            cur.execute("SELECT id, name FROM website ORDER BY id LIMIT 1")
            row = cur.fetchone()
        if not row:
            raise RuntimeError(f"No website found with x_store_code={store_code!r} in {db_name}")
        website_id, website_name = row

        # 1. Pull Homepage
        cur.execute(
            "SELECT arch_db FROM ir_ui_view WHERE key = 'website.homepage' AND website_id = %s ORDER BY id DESC LIMIT 1",
            (website_id,),
        )
        hp_row = cur.fetchone()
        if hp_row:
            hp_arch = _extract_arch(hp_row[0])
            root = etree.fromstring(hp_arch.encode("utf-8"))
            root.set("id", hp_id)
            root.set("name", f"{website_name} Starter Homepage")
            if "t-name" in root.attrib:
                del root.attrib["t-name"]
            # Render inner XML nicely inside <template>
            inner = "".join(etree.tostring(child, encoding="unicode") for child in root)
            hp_xml = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                "<odoo>\n"
                f'    <template id="{hp_id}" name="{escape(website_name)} Starter Homepage">\n'
                f"        {inner.strip()}\n"
                "    </template>\n"
                "</odoo>\n"
            )
            (addon_dir / "views" / "homepage.xml").write_text(hp_xml, encoding="utf-8")
            print(f"Synced DB homepage (website_id={website_id}) -> {addon_dir / 'views' / 'homepage.xml'}")

        # 2. Pull Footer
        cur.execute(
            "SELECT arch_db FROM ir_ui_view WHERE key = 'website.footer_custom' AND website_id = %s ORDER BY id DESC LIMIT 1",
            (website_id,),
        )
        ft_row = cur.fetchone()
        if ft_row:
            ft_arch = _extract_arch(ft_row[0])
            ft_root = etree.fromstring(ft_arch.encode("utf-8"))
            footer_div = ft_root.find(".//div[@id='footer']")
            if footer_div is not None:
                div_xml = etree.tostring(footer_div, encoding="unicode").strip()
                ft_xml = (
                    '<?xml version="1.0" encoding="utf-8"?>\n'
                    "<odoo>\n"
                    f'    <template id="{ft_id}" name="{escape(website_name)} Starter Footer">\n'
                    f"        {div_xml}\n"
                    "    </template>\n"
                    "</odoo>\n"
                )
                (addon_dir / "views" / "footer.xml").write_text(ft_xml, encoding="utf-8")
                print(f"Synced DB footer (website_id={website_id}) -> {addon_dir / 'views' / 'footer.xml'}")

        # 3. Pull extra Builder-created website.page records into views/synced_pages.xml
        cur.execute(
            """
            SELECT p.id, p.url, p.is_published, p.website_indexed, v.key, v.name, v.arch_db
              FROM website_page p
              JOIN ir_ui_view v ON v.id = p.view_id
             WHERE p.website_id = %s
               AND v.key != 'website.homepage'
               AND v.key NOT LIKE 'custom_store.page_%%'
             ORDER BY p.id
            """,
            (website_id,),
        )
        extra_pages = cur.fetchall()
        if extra_pages:
            chunks = ['<?xml version="1.0" encoding="utf-8"?>\n<odoo noupdate="1">\n']
            for pid, url, is_pub, is_idx, vkey, vname, arch_db in extra_pages:
                url_str = _extract_arch(url)
                arch_str = _extract_arch(arch_db)
                vroot = etree.fromstring(arch_str.encode("utf-8"))
                inner = "".join(etree.tostring(c, encoding="unicode") for c in vroot).strip()
                tmpl_id = f"synced_page_{pid}"
                page_id = f"synced_page_rec_{pid}"
                chunks.append(
                    f'    <template id="{tmpl_id}" name="{escape(vname or url_str)}">\n'
                    f"        {inner}\n"
                    "    </template>\n"
                    f'    <record id="{page_id}" model="website.page">\n'
                    f'        <field name="url">{escape(url_str)}</field>\n'
                    f'        <field name="is_published">{bool(is_pub)}</field>\n'
                    f'        <field name="website_indexed">{bool(is_idx)}</field>\n'
                    f'        <field name="view_id" ref="{tmpl_id}"/>\n'
                    "    </record>\n"
                )
            chunks.append("</odoo>\n")
            (addon_dir / "views" / "synced_pages.xml").write_text("".join(chunks), encoding="utf-8")
            print(f"Synced {len(extra_pages)} custom Builder page(s) -> {addon_dir / 'views' / 'synced_pages.xml'}")

    return 0


def push_store(slug: str) -> int:
    module_name, addon_dir, hp_id, ft_id = resolve_addon(slug)
    if not addon_dir.is_dir():
        raise FileNotFoundError(f"Addon directory not found: {addon_dir}")

    store_code = "custom_store" if module_name == "custom_store" else module_name[len("custom_store_"):]
    cfg = odoo_ctl.load_env(ROOT)
    db_name = cfg["ODOO_DB"]
    odoo_bin = ROOT / "odoo" / "odoo-bin"

    # 1. Upgrade the module so edited homepage/footer/shop/SCSS/JS files load into DB
    rc = subprocess.call(
        [sys.executable, str(ROOT / "scripts" / "odoo_ctl.py"), "upgrade", "--skip-pull", "--modules", module_name],
        cwd=str(ROOT),
    )
    if rc != 0:
        return rc

    # 2. Apply homepage & footer starter templates forcibly onto that website's Builder views
    runtime_conf = odoo_ctl.write_runtime_conf(ROOT, cfg)
    py_snippet = (
        f"site = env['website'].search([('x_store_code', '=', {store_code!r})], limit=1); "
        f"assert site, 'Website not found'; "
        f"site._apply_store_homepage_template('{module_name}.{hp_id}', force=True); "
        f"site._apply_store_footer_template('{module_name}.{ft_id}', force=True); "
        "env.cr.commit(); "
        "print('Pushed XML homepage/footer to website ID', site.id)"
    )
    return subprocess.call(
        [sys.executable, str(odoo_bin), "shell", "-c", str(runtime_conf), "-d", db_name, "--no-http"],
        input=py_snippet + "\n",
        text=True,
        cwd=str(ROOT),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Website Builder DB edits <-> addon views.")
    parser.add_argument("action", choices=["pull", "push"], help="'pull' saves DB Builder edits to XML; 'push' applies addon XML to DB")
    parser.add_argument("slug", help="Store slug (e.g. custom_store, fairtag, zoira)")
    args = parser.parse_args()

    if args.action == "pull":
        return pull_store(args.slug)
    return push_store(args.slug)


if __name__ == "__main__":
    raise SystemExit(main())
