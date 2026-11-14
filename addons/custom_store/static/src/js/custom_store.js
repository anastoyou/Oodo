/* @odoo-module */

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

export class CustomStorefront extends Interaction {
    static selector = "#wrapwrap";

    start() {
        // Add storefront JS interactions cleanly here without modifying core odoo/ files.
    }
}

registry
    .category("public.interactions")
    .add("custom_store.storefront", CustomStorefront);

