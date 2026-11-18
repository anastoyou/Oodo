{
    "name": "Custom Omnichannel(C)",
    "version": "20.0.1.0.0",
    "category": "Website/Sales",
    "summary": "eCommerce Subscriptions, Rentals & Drawn PDF e-Sign.",
    "description": """
Omnichannel checkout & signature suite:

- Online /shop subscription & rental checkout auto-provisioning
- HTML5 Canvas drawn e-Signatures with stamped PDF certificates
    """,
    "author": "Custom Store",
    "depends": [
        "custom_store",
        "custom_enterprise",
    ],
    "data": [
        "views/omnichannel_views.xml",
        "views/omnichannel_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}

