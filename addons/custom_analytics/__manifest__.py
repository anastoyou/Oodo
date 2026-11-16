{
    "name": "Custom Analytics Hub (Cross-ERP Visual Dashboard, Graph & Pivot Suite)",
    "version": "20.0.2.0.0",
    "category": "Reporting/Analytics",
    "summary": "All-domain Analytics hub: /analytics Chart.js BI dashboard, Scaling Roadmap Phase 1-5 Progress & Next-Phase Alerts (/analytics/roadmap), Sales/Purchase/Inventory/CRM/Finance/HR/Ops Graph & Pivot",
    "author": "Custom Store",
    "depends": [
        "custom_scaling_ops",
        "analytic",
        "crm",
    ],
    "data": [
        "security/ir.access.csv",
        "data/roadmap_cron.xml",
        "views/analytics_views.xml",
        "views/roadmap_views.xml",
        "views/analytics_templates.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
