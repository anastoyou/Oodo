{
    "name": "Custom Communications (WhatsApp Cloud, VoIP Call Log & Frontdesk Kiosk)",
    "version": "20.0.1.0.0",
    "category": "Discuss/Communications",
    "summary": "WhatsApp Business Cloud API connector & templates, VoIP call logging/click-to-call, and Frontdesk Visitor Check-In Kiosk",
    "author": "Custom Store",
    "depends": [
        "custom_enterprise",
    ],
    "data": [
        "security/ir.access.csv",
        "data/comms_data.xml",
        "views/comms_views.xml",
        "views/frontdesk_templates.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}

