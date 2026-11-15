{
    "name": "Custom Operations UI (Shop Floor, Camera Barcode PWA, Timesheets, Spreadsheets & Studio App)",
    "version": "20.0.1.0.0",
    "category": "Operations/Productivity",
    "summary": "Shop Floor workcenter kiosk (/shopfloor), Camera & Audio Barcode PWA (/barcode), Weekly Timesheets & Timers, Calendar timeline views, Live Formula Spreadsheets, and Studio-Lite App Creator",
    "author": "Custom Store",
    "depends": [
        "custom_enterprise",
    ],
    "data": [
        "security/ir.access.csv",
        "data/operations_data.xml",
        "views/operations_ui_views.xml",
        "views/operations_ui_templates.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}

