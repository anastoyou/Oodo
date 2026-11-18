/* @odoo-module */

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

export class ZoiraStorefront extends Interaction {
    static selector = "html[data-store-code='zoira'] #wrapwrap";

    start() {
        // Add ZOIRA LAWNS-specific JS interactions here without affecting other websites.
    }
}

registry
    .category("public.interactions")
    .add("custom_store_zoira.storefront", ZoiraStorefront);
