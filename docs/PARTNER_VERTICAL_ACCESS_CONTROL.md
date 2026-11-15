# Separate ERP Control per Partner / Vertical (Ladies, Children, Gadgets, Custom Stitches)

When different partners or managers run different lines (for example: Person 1 = **Ladies**, Person 2 = **Children/Kids**, Person 3 = **Gadgets**, Person 4 = **Custom Stitches**), pick the matching isolation level in Odoo `20.0`:

---

## Option 1: App Roles + Sales Teams / Warehouses (Zero Code — One Company)

Best when managers collaborate in one company and only need clean app permissions, queues, and team dashboards:

1. Create an internal user for each manager under **Settings → Users & Companies → Users** and grant only the apps they need (leave Accounting/Invoicing hidden unless they do billing):
   * **Ladies Manager / Children Manager:** `Sales` (`sales_team.group_sale_salesman_all_leads` or `group_sale_salesman`), `Inventory` (`stock.group_stock_user`), `Purchase` (`purchase.group_purchase_user`), `Products / Create`.
   * **Custom Stitches Manager:** Same as above + activate **`mrp`** (*Manufacturing*) and **`mrp_subcontracting`** (*MRP Subcontracting* for tailor job-work) from `odoo/addons/` and grant Manufacturing rights.
   * **Gadgets Manager:** `Sales`, `Inventory`, `Purchase` + **`repair`** (and **Lots & Serial Numbers** for IMEI/warranty).
2. Create separate **Sales Teams** (`crm.team`: *Ladies*, *Children*, *Custom Stitches*, *Gadgets*), assign `user_id` (Team Leader) and `member_ids`, and set each user's `sale_team_id` and `property_warehouse_id` (**Default Warehouse**) on their User form.
3. *(Trade-off)*: Standard `Inventory / User` or `Sales: User: All Documents` roles still let users view records from other categories in shared lists unless you add Option 2 or Option 3 below.

---

## Option 2: Strict Category / Vertical Isolation Inside One Company (`addons/custom_erp/`)

Best when all 4 divisions operate under **one legal company / GSTIN**, but each manager must **only see and edit their own vertical** (products, orders, transfers, production, tickets):

* **Important Odoo `20.0` change (`ir.access`):** Odoo `20.0` replaced `ir.rule` with the unified **`ir.access`** model ([`ir_access.py`](../odoo/odoo/addons/base/models/ir_access.py)), configured in [`addons/custom_erp/security/ir.access.csv`](../addons/custom_erp/security/ir.access.csv):
  * Rows **with a `group_id`** are **permissions** (OR-ed together).
  * Rows **with an empty `group_id`** are **restrictions** (AND-ed across users, narrowing even built-in app access).
* **Implementation steps inside `addons/custom_erp/`:**
  1. **Use / add Product Categories:** [`product_category_data.xml`](../addons/custom_erp/data/product_category_data.xml) already defines `Ladies` (`categ_apparel_ladies`), `Kids` (`categ_apparel_kids`), and `Accessories & Gadgets` (`categ_accessories`). Add `Custom Stitches` (`categ_custom_stitches`) there too.
  2. **Assign vertical(s) on `res.users`:** Extend `res.users` in `addons/custom_erp/models/` with a `Many2many` field `x_allowed_categ_ids` (`product.category`) and a boolean `x_all_verticals` for founders.
  3. **Tag orders / leads / tickets / manufacturing orders by vertical:** Add `x_vertical_categ_id` (or compute/link from order lines/products) on `sale.order`, `purchase.order`, `stock.picking`, `crm.lead`, `custom.support.ticket`, and (for Custom Stitches) `mrp.production` (alongside tailoring measurement fields on `sale.order.line` / `mrp.production`).
  4. **Add `ir.access` restriction rows in `addons/custom_erp/security/ir.access.csv`** (empty `group_id/id`) on `product.template`, `sale.order`, `purchase.order`, `stock.picking`, and `custom.support.ticket`:
     * Bypass the filter for founders and storefront/portal users (`[(1, '=', 1)] if (user.x_all_verticals or user.share) else [...]`), and restrict internal vertical managers with `[('categ_id', 'child_of', user.x_allowed_categ_ids.ids)]` (on `product.template`) or `[('x_vertical_categ_id', 'child_of', user.x_allowed_categ_ids.ids)]` (on orders, transfers, leads, and tickets).
  5. Reload with `.\upgrade.bat --skip-pull` and `.\start.bat`. Founders continue seeing all 4 verticals, while each partner sees only theirs.

---

## Option 3: Full Division Isolation via Multi-Company (+ Multi-Website)

Best when a vertical has its **own partner ownership, bank account, GSTIN, or separate P&L** — especially **Gadgets** or independent divisions:

1. Core models in `zoeemasterdb` (`product.template`, `sale.order`, `stock.picking`, `crm.lead`, `custom.support.ticket`) **already enforce Multi-Company `ir.access` restrictions** (`[('company_id', 'in', company_ids)]`).
2. Create separate Companies under **Settings → Companies** (e.g. *Apparel Studio*, *Gadgets Division*).
3. On each manager's User record (**Settings → Users & Companies → Users**), set `company_ids` (Allowed Companies) and default `company_id` **only to their company**; give **Founders** access to **all companies** for consolidated visibility.
4. Assign each company its own Warehouses, Journals, Products (`company_id` set instead of blank), and Website (`website.company_id`).

