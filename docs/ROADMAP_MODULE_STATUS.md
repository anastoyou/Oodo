# Scaling Roadmap Module Coverage Status

> Status verified against the live `localhost` database, `odoo/addons/`, and `addons/` relative to [`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md).

---

## Phase-by-Phase Coverage Matrix

| Phase | Installed / Ready | In `odoo/addons/` (`uninstalled` / `False` setting) | External / OCA / Not Installed |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **Complete:** `website`, `website_sale`, `sale_management`, `account`, `l10n_in*`, `purchase`, `stock`, `stock_dropshipping`, `stock_delivery`, `payment_razorpay`, `payment_custom`, `crm`, `mass_mailing`, `website_blog`, `im_livechat`, `portal`, `auth_signup`, `custom_erp`, `custom_store` | — | — |
| **Phase 2** | `loyalty`, `sale_loyalty`, `sale_loyalty_delivery`, `website_sale_loyalty` | Modules: `hr_recruitment`, `stock_landed_costs`, `l10n_in_edi`<br>Settings (`False`): `group_stock_multi_locations`, `group_product_pricelist` | OCA: `stock_barcodes`, `rma`, `account_financial_report`, `account_reconcile_oca`<br>3rd-party: courier & marketplace connectors |
| **Phase 3** | — | Modules: `mrp`, `mrp_subcontracting`, `point_of_sale`, `l10n_in_pos`, `pos_razorpay`, `hr`, `hr_attendance`, `hr_holidays`, `hr_expense`<br>Settings (`False`): `group_analytic_accounting`, `group_stock_adv_location` | OCA: `quality_control_oca`, `mis_builder` |
| **Phase 4** | `portal`; `stock.picking.batch` (merged into core `stock` in Odoo 20.0); `custom.support.ticket` (`custom_erp`) | Modules: `purchase_requisition`<br>Settings (`False`): `group_stock_picking_batch`, `group_stock_adv_location` | `helpdesk` is Enterprise-only (`uninstallable`); OCA: `helpdesk_mgmt`, `account_budget_oca`, `payroll`, `stock_inventory` |
| **Phase 5** | `website` (multi-website), `uom` (installed; `group_uom` setting `False`), multi-company | Modules: `repair`<br>Settings (`False`): `group_stock_production_lot`, `group_uom` | OCA: `account_invoice_inter_company`, `purchase_sale_inter_company`; BI: Metabase / Superset |

---

## Notes

* **`stock_picking_batch` in Odoo `20.0`:** Core Batch Transfers (`stock.picking.batch`) are built directly into `odoo/addons/stock/` ([`stock_picking_batch.py`](../odoo/addons/stock/models/stock_picking_batch.py)) rather than a separate module; toggle `group_stock_picking_batch` in Inventory settings when ready.
* **`odoo` MCP Server DB Configuration:** Ensure any configured `odoo` MCP plugin targets `ODOO_DB=localhost` to match [`.env`](../.env) (rather than any stale database name such as `fairtag`).

