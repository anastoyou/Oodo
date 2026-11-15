# 2-Partner Accounting: Initial Capital, Expenses & Salaries (`l10n_in`)

Your local database is configured with **India (`IN` / `INR`)** localization (`l10n_in`), including journals `Bank (BNK1)`, `Sales (INV)`, `Purchases (BILL)`, and `Miscellaneous Operations (MISC)`.

---

## Step 0: Unhide Full Accounting Menus (Required Once per User)

In Odoo `20.0` Community (`account`), `Administrator` does **not** automatically enable **Journal Entries** and **Chart of Accounts** (they require `Show Accounting Features - Readonly` / `Show Full Accounting Features`):

1. Go to **Settings → Activate the developer mode**.
2. Open **Settings → Users & Companies → Users → your Admin user**.
3. Enable **Show Full Accounting Features**, save, and refresh.
4. **Invoicing → Accounting → Transactions → Journal Entries** and **Invoicing → Configuration → Accounting → Chart of Accounts** will now appear.

---

## 1. Recording Initial Investments (2 Partners)

Your Chart of Accounts already includes **`Capital Account`** (`equity`) and **`Bank`** (`1003`, `asset_cash`).

1. Create two contacts in **Contacts**: **Partner A** and **Partner B**.
2. *(Recommended for clean reporting)* Under **Invoicing → Configuration → Chart of Accounts**, create equity sub-accounts such as `Partner A - Capital Account` and `Partner B - Capital Account` (type: `Equity`), or track both on **`Capital Account`** using the **Partner** column.
3. For each capital deposit, open **Invoicing → Accounting → Journal Entries → New**:
   * **Debit:** `Bank` (`1003`) for the deposited amount
   * **Credit:** `Capital Account` (or `Partner A / B Capital`) with **Partner** set to Partner A or Partner B
   * Click **Post**.
   *(If depositing physical cash instead of a bank transfer, first create a `Cash` journal in **Invoicing → Configuration → Journals**.)*

---

## 2. Recording Partner Expenses (Do You Need an Extra Module?)

* **Paid directly from Company Bank / UPI / Card** (Meta ads, courier, rent, packaging, inventory):
  * **No extra module needed.** Go to **Invoicing → Vendors → Bills → New**, select the vendor, GST tax, and expense account (your `l10n_in` Chart of Accounts already has `Advertisement Expense`, `Office Rent`, `Postage And Courier Expense`, `Job Work Expense`, `Professional Fees`, etc.), post, and click **Pay** from **Bank (`BNK1`)**. *(Aligns with [`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md#L189).)*
* **Paid out of Partner A or B's personal pocket (reimbursement):**
  * **Without adding a module:** Record a Vendor Bill or Journal Entry crediting that partner's Payable / Reimbursement / Capital account until reimbursed from `Bank`.
  * **With Odoo's built-in `Expenses` app (optional):** Activate **`hr_expense`** (already in [`odoo/addons/hr_expense/`](../odoo/addons/hr_expense/__manifest__.py); depends on **`hr`** Employees). Each partner logs bills as *Paid by Employee (to reimburse)* vs *Paid by Company*, approves them, and settles balances cleanly.

---

## 3. Managing Partner Salaries / Drawings & Early Staff Pay

Your Chart of Accounts already includes **`Salary Expense`** (`expense`) and **`Salary Exp Payable`** (`liability_current`).

* **Do you need Payroll in Phase 1–2?** **No.** Odoo's `hr_payroll` is Enterprise-only, so full staff payroll is built as a custom module in **`addons/custom_enterprise/`** (`custom.hr.payslip`, `custom.salary.structure` with `IN_STD` Indian rules, PDF Payslip report, and Accounting Journal Entry posting) for when you add salaried staff, alongside optional **OCA `payroll`** in Phase 3–4+ ([`SCALING_ROADMAP.md`](./SCALING_ROADMAP.md)).
* **Monthly workflow for 2 partners & early helpers:**
  1. Confirm with your CA whether partner payouts should hit `Salary Expense` (Pvt Ltd director salary / LLP remuneration) or a `Partner Drawings` equity account (Partnership / Proprietorship).
  2. Post a monthly **Journal Entry** (or **Vendor Bill**):
     * **Debit:** `Salary Expense` (or `Partner Drawings` / `Professional Fees` for freelancers like CA, photographer, part-time packer/WFH support)
     * **Credit:** `Salary Exp Payable` (with **Partner** = Partner A / Partner B)
  3. When transferring cash from the company bank, record the payout under **Invoicing → Vendors → Payments** (`Bank (BNK1)`) and reconcile it against `Salary Exp Payable`.

