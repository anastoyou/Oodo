{
    "name": "FAIRTAG Storefront",
    "version": "20.0.1.0.0",
    "category": "Website/eCommerce",
    "summary": "Isolated, Builder-compatible storefront for FAIRTAG (custom_store_fairtag).",
    "author": "ZOEE GLOBAL PRIVATE LIMITED",
    "depends": [
        "custom_store",
    ],
    "data": [
        "views/header.xml",
        "views/homepage.xml",
        "views/footer.xml",
        "views/shop_templates.xml",
        "views/product_templates.xml",
        "views/cart_templates.xml",
        "views/checkout_templates.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
