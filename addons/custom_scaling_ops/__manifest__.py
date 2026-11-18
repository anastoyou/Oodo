{
    "name": "Custom Scaling Ops – Phase 2-5(C)",
    "version": "20.0.1.0.0",
    "category": "Operations/Scaling",
    "summary": "RMA Exchanges, Courier AWB, Marketplaces & Hang-Tags.",
    "description": """
Phase 2-5 scaling toolkit:

- RMA & size exchanges
- Shiprocket/Delhivery courier AWB & webhook
- Myntra/Amazon/Flipkart/Meesho feed & order CSV sync
- Thermal Apparel Hang-Tag PDF labels & Barcode Camera Push-to-Session
- Gadget Warranty Claims & Franchise Inter-Company PO->SO sync
    """,
    "author": "Custom Store",
    "depends": [
        "custom_erp",
        "custom_operations_ui",
        "purchase",
    ],
    "data": [
        "security/ir.access.csv",
        "data/scaling_ops_data.xml",
        "views/report_hangtag.xml",
        "views/scaling_ops_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}

