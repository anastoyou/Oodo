# Per-Website, Per-Product Custom PDP Engine (`new_pdp.bat`)

Build isolated, bespoke Product Detail Pages (`/shop/<product>`) for a **specific website + specific product** without modifying `odoo/` core files or affecting other websites/products.

Supports two code modes:
1. **`native` (Native QWeb with Page Builder):** Odoo QWeb XML editable both in code and visually via Odoo's **Edit (Website Builder)** mode.
2. **`react` (React + TypeScript + Tailwind CSS):** Self-contained Vite + React (`.tsx`) + Tailwind bundle mounted inside the site's Header & Footer, wired to Odoo 20's live pricing, variants, cart, checkout, wishlist, compare, documents, and stock alerts. Every React PDP generates two TSX files:
   - `PdpPage.tsx` — customer-facing product UI.
   - `pdppage_full_data.tsx` — **developer-only** all-options holder & feature reference page (never visible to customers).

---

## 1. Directory & Database Architecture

Each custom PDP lives inside its website's store addon (`addons/custom_store/`, `addons/custom_store_fairtag/`, `addons/custom_store_zoira/`, etc.):

```text
addons/<store_addon>/
├── custom_pdp/
│   └── <product_id>_<slug>/
│       ├── pdp.json                    # Metadata (website_id, product_id, mode, paths)
│       ├── native/                     # Created when mode = "native"
│       │   └── pdp_<id>_<slug>.xml
│       └── react/                      # Created when mode = "react"
│           ├── PdpPage.tsx             # Customer-facing React + TypeScript + Tailwind UI
│           ├── pdppage_full_data.tsx   # Developer-only all-options holder (COPY BLOCKs + live feature snapshot)
│           └── pdp.css                 # Optional per-product CSS
└── static/
    └── dist/
        └── pdp_<id>_<slug>/            # Compiled Vite bundles (mode = "react")
            ├── pdp.js
            ├── pdp.css
            ├── pdp_full_data.js
            └── pdp_full_data.css
```

### How Odoo Dispatches It
- **Database Mapping (`custom.store.product.pdp`):** Defined in [`addons/custom_store/models/product_pdp.py`](../addons/custom_store/models/product_pdp.py), enforcing one active custom PDP entry per `(website_id, product_tmpl_id)`.
- **Controller Hook (`CustomStoreWebsiteSale.product`):** Defined in [`addons/custom_store/controllers/main.py`](../addons/custom_store/controllers/main.py). Calls `super().product(...)` first (preserving permissions, pricelists, and canonical redirects), then swaps the rendered template:
  - `native` → website-scoped `ir.ui.view` (`<store_addon>.pdp_<id>_<slug>`)
  - `react` → `custom_store.react_pdp_shell` ([`addons/custom_store/views/custom_pdp_views.xml`](../addons/custom_store/views/custom_pdp_views.xml)), keeping the site's Header & Footer and injecting `data-bootstrap` JSON + `?v=<mtime>` cache-busted bundle links.
  - **Developer-only `?pdp_dev=full` preview:** Only authenticated users with `website.group_website_restricted_editor` visiting the canonical PDP URL with `?pdp_dev=full` load `pdp_full_data.js` (`pdppage_full_data.tsx`). Public/portal visitors always receive `pdp.js` (`PdpPage.tsx`), even if `?pdp_dev=full` is appended to the URL.
- **Backend Visibility (Administrators & Website Designers only):**
  - Manage overrides under **Website → Configuration → Custom PDPs** (Administrators), or on a product's **Custom PDPs** tab (`website.group_website_designer` / Administrators, only shown when a custom PDP exists).
  - Manual "Add a line" / "New" creation in Odoo UI is disabled to prevent broken un-scaffolded rows; create new custom PDPs with `.\new_pdp.bat`.
  - Toggle **Enabled** OFF to fall back to the default Odoo product page while keeping your code files intact on disk (the row stays visible so you can re-enable it anytime). Use **Delete Code** (or `.\new_pdp.bat --remove`) to permanently delete the override and remove the code folder from disk.

---

## 2. Creating a Custom PDP (`new_pdp.bat`)

Run the interactive launcher from the repo root:

```bat
.\new_pdp.bat
```

It walks through:
1. **Choose Website** (lists all `website` records and their mapped `custom_store*` addon).
2. **Choose Product** (lists active products visible on that site; type `/<keyword>` to filter by name, SKU, or ID).
3. **Choose Code Type**:
   - `[1] Native with Page Builder` — scaffolds `native/pdp_<id>_<slug>.xml` and registers the `ir.ui.view`.
   - `[2] React + Tailwind CSS (TypeScript)` — scaffolds `react/PdpPage.tsx`, `react/pdppage_full_data.tsx`, and `pdp.css`, runs the Vite + Tailwind build (`frontend_pdp/`), and registers both compiled `pdp.js`/`pdp.css` (customer) and `pdp_full_data.js`/`pdp_full_data.css` (developer reference).

### Non-Interactive CLI Flags

| Command | What it does |
| :--- | :--- |
| `.\new_pdp.bat --website fairtag --product 12 --type react` | Create & build a React + TypeScript + Tailwind PDP (`PdpPage.tsx` + `pdppage_full_data.tsx`) |
| `.\new_pdp.bat --website fairtag --product 12 --type native` | Create a Native QWeb / Page Builder PDP directly |
| `.\new_pdp.bat --watch --target custom_store_fairtag/12_kurti` | Watch & auto-rebuild React TSX/Tailwind on save (`pdp.js` and `pdp_full_data.js`) |
| `.\new_pdp.bat --build` | Rebuild all React PDPs across all `custom_store*` addons |
| `.\new_pdp.bat --build --target 12_kurti` | Rebuild one React PDP bundle |
| `.\new_pdp.bat --pull --target 12_kurti` | Pull Website Builder DB edits into `native/pdp_<id>_<slug>.xml` |
| `.\new_pdp.bat --sync` | Push all disk `native` XML / `react` bundles back into Odoo DB & sync `pdppage_full_data.tsx` |
| `.\new_pdp.bat --remove --website fairtag --product 12` | Unlink the mapping, DB view, and disk folders |
| `cd frontend_pdp && npm.cmd run typecheck` | Run TypeScript checking (`tsc --noEmit`) across `frontend_pdp/src` and all `react/*.tsx` PDPs |

> **First-time server note:** After upgrading `custom_store`, restart `odoo-bin` once so the running HTTP worker loads [`controllers/main.py`](../addons/custom_store/controllers/main.py) and [`models/product_pdp.py`](../addons/custom_store/models/product_pdp.py). For `react` PDPs added afterward, rebuilding (`--build` / `--watch`) takes effect immediately on page refresh.

---

## 3. Customizing a `react` PDP (`PdpPage.tsx` & `pdppage_full_data.tsx`)

- **Customer UI:** Edit `addons/<store_addon>/custom_pdp/<id>_<slug>/react/PdpPage.tsx` while running watch mode:
  ```bat
  .\new_pdp.bat --watch --target <store_addon>/<id>_<slug>
  ```
- **Developer All-Options Holder (`pdppage_full_data.tsx`):**
  - Open `pdppage_full_data.tsx` in your editor (or visit `/shop/<product-slug>-<id>?pdp_dev=full` signed in as an Odoo Website Editor / Administrator).
  - Contains `export const DETECTED_ODOO_FEATURES = { ... };` (an auto-synced snapshot of enabled Odoo product fields, media URLs, video URLs, variants, ribbon, tags, documents, cross-sell links, UoMs, and website eCommerce options) plus labeled `{/* === COPY BLOCK: ... === */}` TSX sections you can copy directly into `PdpPage.tsx`:
    1. Breadcrumbs
    2. Ribbon, Product Tags & Customer Rating
    3. Media Gallery (Images + Video URLs / `embed_code`)
    4. Product Title, SKU, Pricing, Tax Indication & Short Description
    5. Dynamic Variant Attributes (`radio`, `pills`, `select`, `color`, `multi`, `is_custom`)
    6. Stock / Quantity / UoM / Add to Cart / Buy Now / Wishlist / Compare / Out-of-Stock Notify Me
    7. Apparel Specs & Product Documents
    8. Optional / Accessory / Alternative Products
    9. Rich eCommerce Copy & Bottom Website Description & Raw Bootstrap JSON toggle
  - **Automatic Sync on Odoo Changes:** Post-commit hooks in [`addons/custom_store/models/product_pdp.py`](../addons/custom_store/models/product_pdp.py) (`ProductTemplate.write`, `ProductImage` create/write/unlink, `ProductTemplateAttributeLine` create/write/unlink, `IrUiViewPdpSync.write` on `website_sale.*` keys) automatically update `DETECTED_ODOO_FEATURES` inside `pdppage_full_data.tsx` whenever you change product data, media, variants, or website settings in Odoo (while live `?pdp_dev=full` requests always read the latest runtime `bootstrap` payload from Odoo).

### Shared Odoo Hook: `useOdooPdp(bootstrap)`
Defined in [`frontend_pdp/src/useOdooPdp.ts`](../frontend_pdp/src/useOdooPdp.ts) with TypeScript types in [`frontend_pdp/src/types.ts`](../frontend_pdp/src/types.ts), it connects your React UI directly to Odoo 20's native `website_sale` JSON-RPC routes (`/website_sale/get_combination_info`, `/sale/create_product_variant`, `/shop/cart/add`, `/shop/wishlist/add`, `/shop/add/stock_notification`):

| Property / Method | Description |
| :--- | :--- |
| `website`, `currency` | Active Odoo `website` (`id`, `name`, `store_code`) and `currency` formatting config |
| `product` | `id`, `name`, `default_code`, `description_sale`, `description_ecommerce`, `website_description`, `specs` (`x_fabric`, `x_fit_type_label`, `x_wash_care`, `x_dispatch_days`), `categories`, `uoms`, `ribbon`, `tags`, `documents`, `optional_products`, `accessory_products`, `alternative_products`, `rating` |
| `combinationInfo` | Live variant `product_id`, `display_name`, `price`, `compare_list_price`, `has_discounted_price`, `is_sold_out`, `free_qty`, `prevent_sale`, `is_in_wishlist`, `has_stock_notification` |
| `attributeLines`, `selectedByLine`, `selectValue(ptalId, ptavId, isMulti)` | Dynamic attribute/variant selectors (`radio`, `pills`, `select`, `color`, `multi`) + `isValueExcluded(ptavId)` |
| `customValues`, `setCustomValue(ptavId, text)` | Handles attributes marked `is_custom` |
| `images`, `activeImageIdx`, `setActiveImageIdx` | Gallery images and video URLs / `embed_code` (automatically updated when variant changes) |
| `qty`, `setQty`, `uomId`, `selectUom` | Quantity and packaging/UoM selection |
| `options`, `routes`, `compareUrl` | Feature flags (`show_quantity`, `buy_now_enabled`, `wishlist_enabled`, `compare_enabled`, `tax_indication_enabled`, etc.), Odoo endpoint routes, and `/shop/compare?products=...` URL |
| `addToCart(opts?)` | Calls `/shop/cart/add` (supports optional `overrideProductTemplateId`, `overrideProductId`, `overrideQty`), syncs navbar `.my_cart_quantity` badge, sets `feedback` |
| `buyNow(redirectTo)` | Adds to cart and redirects to `/shop/checkout` (or custom URL) |
| `toggleWishlist()` | Calls `/shop/wishlist/add` and updates navbar wishlist badge (when active) |
| `subscribeStockNotification(email)` | Subscribes back-in-stock alerts when `is_sold_out` |
| `formatMoney(amount)` | Formats amounts using the website's Odoo currency symbol, position, and precision |

### Tailwind & Bootstrap 5 Isolation
[`frontend_pdp/tailwind.config.js`](../frontend_pdp/tailwind.config.js) sets:
- `corePlugins: { preflight: false }` — prevents Tailwind's CSS reset from altering Odoo's Bootstrap 5 navbar, footer, or cart modals.
- `important: "#custom-react-pdp-root"` — scopes Tailwind utility specificity inside your React PDP container.

---

## 4. Customizing a `native` PDP (QWeb + Website Builder)

- **Code-first:** Edit `addons/<store_addon>/custom_pdp/<id>_<slug>/native/pdp_<id>_<slug>.xml`, then run:
  ```bat
  .\new_pdp.bat --sync --target <id>_<slug>
  ```
- **Visual-first:** Open `/shop/<product>` in the browser, click **Edit** (top-right), drag blocks inside `#wrap` (`oe_structure`), save, and optionally export changes back to disk with:
  ```bat
  .\new_pdp.bat --pull --target <id>_<slug>
  ```

---

## 5. Automatic Cleanup When Deleting a Product

- When you delete a `product.template` in Odoo, [`ProductTemplate.unlink()`](../addons/custom_store/models/product_pdp.py) snapshots any linked `custom.store.product.pdp` folders and `ir.ui.view` records, deletes the DB records, and registers an **`env.cr.postcommit`** callback to remove:
  - `addons/<store_addon>/custom_pdp/<id>_<slug>/`
  - `addons/<store_addon>/static/dist/pdp_<id>_<slug>/`
- **Rollback safety:** If `unlink()` fails (for example, a foreign-key restriction from an existing sales order or invoice) or the transaction rolls back, **no files are deleted on disk**.
- **Archiving:** Archiving a product (`active = False`) preserves all custom PDP files and mappings.
