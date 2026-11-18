/* @odoo-module */

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

export class FairtagStorefront extends Interaction {
    static selector = "html[data-store-code='fairtag'] #wrapwrap";

    start() {
        // Add FAIRTAG-specific JS interactions here without affecting other websites.
    }
}

registry
    .category("public.interactions")
    .add("custom_store_fairtag.storefront", FairtagStorefront);
