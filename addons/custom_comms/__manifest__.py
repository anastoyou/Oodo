{
    "name": "Custom Communications(C)",
    "version": "20.0.1.0.0",
    "category": "Discuss/Communications",
    "summary": "WhatsApp Cloud API, VoIP Call Log & Frontdesk Kiosk.",
    "description": """
Unified business communications suite:

- WhatsApp Business Cloud API connector & templates
- VoIP call logging & click-to-call
- Frontdesk Visitor Check-In Kiosk
    """,
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

