# Odoo Storefront & Backend URLs

> **Note:** `https://dollar-observations-silicon-leeds.trycloudflare.com` is an active temporary Cloudflare Quick Tunnel (`trycloudflare.com`) forwarding to `http://localhost:8069`. If the tunnel process is restarted, a new public hostname will be generated.

## Main Website & eCommerce URLs

| Section | Local URL | Public Tunnel URL |
|---|---|---|
| **Website (Homepage)** | http://localhost:8069/ | https://dollar-observations-silicon-leeds.trycloudflare.com/ |
| **eCommerce (Shop Catalog)** | http://localhost:8069/shop | https://dollar-observations-silicon-leeds.trycloudflare.com/shop |

---

## Cart, Checkout, Portal, Support & Backend URLs

| Page / Feature | Local URL | Public Tunnel URL |
|---|---|---|
| **Shopping Cart** | http://localhost:8069/shop/cart | https://dollar-observations-silicon-leeds.trycloudflare.com/shop/cart |
| **Checkout** *(requires items in cart)* | http://localhost:8069/shop/checkout | https://dollar-observations-silicon-leeds.trycloudflare.com/shop/checkout |
| **Customer Portal Dashboard** | http://localhost:8069/my | https://dollar-observations-silicon-leeds.trycloudflare.com/my |
| **Customer Orders** | http://localhost:8069/my/orders | https://dollar-observations-silicon-leeds.trycloudflare.com/my/orders |
| **Customer Support Tickets** | http://localhost:8069/my/tickets | https://dollar-observations-silicon-leeds.trycloudflare.com/my/tickets |
| **Support & Exchange Request Page** | http://localhost:8069/support | https://dollar-observations-silicon-leeds.trycloudflare.com/support |
| **Apparel Size Guide** | http://localhost:8069/size-guide | https://dollar-observations-silicon-leeds.trycloudflare.com/size-guide |
| **Shipping & Dispatch Policy** | http://localhost:8069/shipping-policy | https://dollar-observations-silicon-leeds.trycloudflare.com/shipping-policy |
| **Returns & Size Exchange Policy** | http://localhost:8069/return-policy | https://dollar-observations-silicon-leeds.trycloudflare.com/return-policy |
| **Blog** | http://localhost:8069/blog | https://dollar-observations-silicon-leeds.trycloudflare.com/blog |
| **Login** | http://localhost:8069/web/login | https://dollar-observations-silicon-leeds.trycloudflare.com/web/login |
| **Customer Signup** | http://localhost:8069/web/signup | https://dollar-observations-silicon-leeds.trycloudflare.com/web/signup |
| **Odoo Admin Backend (ERP / Builder)** | http://localhost:8069/odoo | https://dollar-observations-silicon-leeds.trycloudflare.com/odoo |











---

## Running & Multi-Store Commands

```powershell
# Start local Odoo server
.\.venv\Scripts\python.exe .\odoo\odoo-bin -c .\odoo.conf

# Upgrade custom addons (stops local Odoo, backs up DB, upgrades)
.\upgrade.bat --skip-pull

# Create & install a new isolated, Builder-compatible store addon (addons/custom_store_<slug>/)
.\new_store.bat fairtag "FAIRTAG" --company "FAIRTAG" --domain "http://fairtag.localhost:8069" --install
.\new_store.bat zoira "ZOIRA LAWNS" --company "ZOIRA LAWNS" --domain "http://zoira.localhost:8069" --install

# Sync Website Builder edits <-> addon XML (views/homepage.xml, footer.xml, synced_pages.xml)
.\sync_store.bat pull fairtag
.\sync_store.bat push fairtag
```



