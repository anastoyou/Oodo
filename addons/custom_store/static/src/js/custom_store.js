/* @odoo-module */

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

export class CustomStorefront extends Interaction {
    static selector = "html[data-store-code='custom_store'] #wrapwrap";

    start() {
        // Add Website 1 storefront JS interactions cleanly here without affecting other websites.
    }
}

registry
    .category("public.interactions")
    .add("custom_store.storefront", CustomStorefront);
