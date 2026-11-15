# Scaling Roadmap Module Coverage Status

> Status verified against the live `zoeemasterdb` database, `odoo/addons/`, and `addons/` relative to [`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md).

---

## Phase-by-Phase Coverage Matrix

| Phase | Installed / Ready | In `odoo/addons/` (`uninstalled` / `False` setting) | External / OCA / Not Installed |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **Complete:** `website`, `website_sale`, `sale_management`, `account`, `l10n_in*`, `purchase`, `stock`, `stock_dropshipping`, `stock_delivery`, `payment_razorpay`, `payment_custom`, `crm`, `im_livechat`, `mass_mailing`, `website_blog`, `portal`, `auth_signup`, `custom_erp`, `custom_store`, **`custom_enterprise`**, **`custom_accounting_pro`** (Interactive Bank Reconcile, Bill PDF OCR, Auto-Asset on Post, Consolidation/Cash Flow, Tax Lock, Equity Cap Table), **`custom_comms`** (WhatsApp Cloud/Webhook, VoIP Log, Frontdesk `/frontdesk`), **`custom_omnichannel`** (`/shop` Subscriptions & Rentals, Canvas & Stamped PDF e-Sign), **`custom_operations_ui`** (`/shopfloor`, Camera `/barcode`, Timesheets/Timers, Planning/Rental Calendars, Live Formula Spreadsheets, Studio App Builder) | — | — |
| **Phase 2** | `loyalty`, `sale_loyalty`, `sale_loyalty_delivery`, `website_sale_loyalty`; **`custom_enterprise`:** Barcode Scan Console (`custom.barcode.session`), Quality Control (`custom.quality.check`), Bank Auto-Reconcile & Budgets; **`custom_scaling_ops`:** Returns & Size-Exchange RMA (`custom.rma.request`), Shiprocket/Delhivery Courier AWB & Pincode Rules, Marketplace Feed/Order CSV Sync, Apparel Hang-Tag Barcode Labels | Modules: `hr_recruitment`, `stock_landed_costs`, `l10n_in_edi`<br>Settings (`False`): `group_stock_multi_locations`, `group_product_pricelist` | Optional OCA upgrades: `account_financial_report`, `account_reconcile_oca`<br>Live marketplace/courier keys entered when activated |
| **Phase 3** | **`custom_enterprise`:** Payroll (`custom.hr.payslip`), Appraisals (`custom.hr.appraisal`), Shift Planning (`custom.planning.shift`), PLM Tech Packs & ECOs | Modules: `mrp`, `mrp_subcontracting`, `point_of_sale`, `l10n_in_pos`, `pos_razorpay`, `hr_attendance`, `hr_holidays`, `hr_expense`<br>Settings (`False`): `group_analytic_accounting`, `group_stock_adv_location` | Optional OCA: `mis_builder` |
| **Phase 4** | `portal`; `stock.picking.batch` (merged into core `stock` in Odoo 20.0); `custom.support.ticket` (`custom_erp`); **`custom_enterprise`:** Helpdesk SLA/Teams/CSAT, Multi-Step Approvals (`custom.approval.request`), DMS (`custom.document`), Field Service (`custom.field.service.task`), Executive KPIs (`custom.kpi.snapshot`) | Modules: `purchase_requisition`<br>Settings (`False`): `group_stock_picking_batch`, `group_stock_adv_location` | Optional OCA: `helpdesk_mgmt`, `stock_inventory` (core Enterprise gaps now built in `custom_enterprise`) |
| **Phase 5** | `website` (multi-website), `uom` (installed; `group_uom` setting `False`), multi-company; **`custom_enterprise`:** Subscriptions, Rentals, e-Sign, Marketing Automation, Social Planner; **`custom_scaling_ops`:** Gadget Warranty Claims (`custom.warranty.claim`), Franchise Inter-Company PO → SO Sync (`custom.intercompany.rule`) | Modules: `repair`<br>Settings (`False`): `group_stock_production_lot`, `group_uom` | BI: Metabase / Superset (alongside `custom_operations_ui` Formula Spreadsheets) |

---

## Notes

* **`stock_picking_batch` in Odoo `20.0`:** Core Batch Transfers (`stock.picking.batch`) are built directly into `odoo/addons/stock/` ([`stock_picking_batch.py`](../odoo/addons/stock/models/stock_picking_batch.py)) rather than a separate module; toggle `group_stock_picking_batch` in Inventory settings when ready.
* **`odoo` MCP Server DB Configuration:** Ensure any configured `odoo` MCP plugin targets `ODOO_DB=zoeemasterdb` to match [`.env`](../.env) (rather than any stale database name such as `fairtag` or `localhost`).

