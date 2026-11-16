{
    "name": "Custom Instagram Business & Unit DM Commerce",
    "version": "20.0.1.0.0",
    "category": "Sales/Social",
    "summary": "Per-Unit Instagram API with Instagram Login (60-day auto-refresh token), Automatic Product-to-Instagram Sync, Meesho-style Direct Product Link DM Cards & Comment-to-DM Webhooks",
    "author": "Custom Store",
    "depends": [
        "custom_erp",
        "custom_store",
        "website_sale",
        "crm",
        "mail",
    ],
    "data": [
        "security/ir.access.csv",
        "data/instagram_data.xml",
        "views/instagram_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}

