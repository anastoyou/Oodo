/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const PRODUCT_LINK_CONTAINERS = [
    ".oe_product_cart",
    ".oe_product",
    ".o_carousel_product_card",
    ".o_wishlist_item",
    ".o_wsale_compare_table_column",
    "#suggested_products",
    "#cart_products",
].join(", ");

const PRODUCT_LINK_QUERY = [
    ".oe_product_cart a[href]",
    ".oe_product a[href]",
    ".o_carousel_product_card a[href]",
    ".o_wishlist_item a[href]",
    ".o_wsale_compare_table_column a[href]",
    "#suggested_products a[href]",
    "#cart_products a[href]",
].join(", ");

const NON_PDP_SHOP_PREFIXES = [
    "/shop/category",
    "/shop/page",
    "/shop/cart",
    "/shop/wishlist",
    "/shop/compare",
    "/shop/checkout",
    "/shop/address",
    "/shop/extra_info",
    "/shop/payment",
    "/shop/confirmation",
    "/shop/pricelist",
    "/shop/change_pricelist",
    "/shop/print",
    "/shop/terms",
    "/shop/config",
    "/shop/products",
    "/shop/reload",
    "/shop/donation",
];

const INTERACTIVE_CARD_TARGETS = [
    "a",
    "button",
    "input",
    "select",
    "textarea",
    "label",
    "[role='button']",
    ".o_wsale_product_btn",
    ".o_wsale_attribute_previewer",
    ".js_remove",
    ".o_carousel_product_remove",
    ".o_comparelist_remove",
    ".carousel-control-prev",
    ".carousel-control-next",
    ".carousel-indicators",
].join(", ");

function isEditorActive(el) {
    if (document.body?.classList.contains("editor_enable")) {
        return true;
    }
    return Boolean(el?.closest?.(".editor_enable, [contenteditable='true']"));
}

function isProductDetailUrl(rawHref) {
    if (!rawHref) {
        return false;
    }
    const trimmed = rawHref.trim();
    if (
        !trimmed ||
        trimmed === "#" ||
        trimmed.startsWith("javascript:") ||
        trimmed.startsWith("mailto:") ||
        trimmed.startsWith("tel:")
    ) {
        return false;
    }

    let parsed;
    try {
        parsed = new URL(trimmed, window.location.origin);
    } catch {
        return false;
    }
    if (parsed.origin !== window.location.origin) {
        return false;
    }

    // Strip optional Odoo multi-language path prefix (e.g. /en_US/shop/... or /fr/shop/...).
    const langMatch = parsed.pathname.match(
        /^(?:\/[a-z]{2,3}(?:[_-][A-Za-z0-9]{2,6})?)?(\/shop\/.+)$/
    );
    if (!langMatch) {
        return false;
    }

    const shopPath = langMatch[1].replace(/\/+$/, "");
    if (!shopPath || shopPath === "/shop") {
        return false;
    }

    if (
        NON_PDP_SHOP_PREFIXES.some(
            (prefix) => shopPath === prefix || shopPath.startsWith(`${prefix}/`)
        )
    ) {
        return false;
    }

    // Exclude downloadable product document links (/shop/<slug>/document/<id>).
    if (/\/document\/\d+$/.test(shopPath)) {
        return false;
    }

    return true;
}

function shouldAnnotateAnchor(anchor) {
    if (!(anchor instanceof HTMLAnchorElement)) {
        return false;
    }
    if (anchor.classList.contains("btn") || anchor.closest(".o_wsale_product_btn")) {
        return false;
    }
    if (!anchor.closest(PRODUCT_LINK_CONTAINERS)) {
        return false;
    }
    return isProductDetailUrl(anchor.getAttribute("href"));
}

function markAnchorNewTab(anchor) {
    if (anchor.getAttribute("target") !== "_blank") {
        anchor.setAttribute("target", "_blank");
    }
    const relTokens = new Set(
        (anchor.getAttribute("rel") || "")
            .split(/\s+/)
            .map((token) => token.trim())
            .filter(Boolean)
    );
    if (!relTokens.has("noopener") || !relTokens.has("noreferrer")) {
        relTokens.add("noopener");
        relTokens.add("noreferrer");
        anchor.setAttribute("rel", Array.from(relTokens).join(" "));
    }
    anchor.dataset.csProductLink = "1";
}

function getCardPrimaryProductUrl(card) {
    if (!card) {
        return null;
    }
    const candidates = [
        card.querySelector("a.oe_product_image_link[href]"),
        card.querySelector(".o_wsale_products_item_title a[href]"),
        ...card.querySelectorAll("a[href]"),
    ];
    for (const candidate of candidates) {
        if (candidate && shouldAnnotateAnchor(candidate)) {
            return candidate.href;
        }
    }
    return null;
}

function annotateSubtree(rootEl) {
    if (!(rootEl instanceof Element) || isEditorActive(rootEl)) {
        return;
    }

    const anchors = new Set();
    if (rootEl.matches("a[href]")) {
        anchors.add(rootEl);
    }
    if (rootEl.matches(PRODUCT_LINK_CONTAINERS)) {
        rootEl.querySelectorAll("a[href]").forEach((anchor) => anchors.add(anchor));
    } else {
        rootEl.querySelectorAll(PRODUCT_LINK_QUERY).forEach((anchor) => anchors.add(anchor));
    }

    for (const anchor of anchors) {
        if (shouldAnnotateAnchor(anchor)) {
            markAnchorNewTab(anchor);
        }
    }

    const cards = new Set();
    if (rootEl.matches(".oe_product_cart")) {
        cards.add(rootEl);
    }
    rootEl.querySelectorAll(".oe_product_cart").forEach((card) => cards.add(card));

    for (const card of cards) {
        if (getCardPrimaryProductUrl(card)) {
            card.dataset.csProductNewTab = "1";
        } else {
            delete card.dataset.csProductNewTab;
        }
    }
}

export class ProductNewTab extends Interaction {
    static selector = "#wrapwrap";
    dynamicContent = {
        _root: {
            "t-on-click.noUpdate": this.onCardClick,
            "t-on-auxclick.noUpdate": this.onCardAuxClick,
        },
    };

    start() {
        annotateSubtree(this.el);

        const observer = new MutationObserver((mutations) => {
            if (isEditorActive(this.el)) {
                return;
            }
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node instanceof Element) {
                        annotateSubtree(node);
                    }
                }
            }
        });
        observer.observe(this.el, {
            childList: true,
            subtree: true,
        });
        this.registerCleanup(() => {
            observer.disconnect();
            this.el.querySelectorAll(".oe_product_cart[data-cs-product-new-tab]").forEach((card) => {
                delete card.dataset.csProductNewTab;
            });
        });
    }

    onCardClick(ev) {
        if (ev.button !== 0 || ev.altKey) {
            return;
        }
        this._openCardIfEligible(ev);
    }

    onCardAuxClick(ev) {
        if (ev.button !== 1) {
            return;
        }
        this._openCardIfEligible(ev);
    }

    _openCardIfEligible(ev) {
        if (ev.defaultPrevented || isEditorActive(ev.target)) {
            return;
        }
        if (ev.target.closest(INTERACTIVE_CARD_TARGETS)) {
            return;
        }
        const selection = window.getSelection?.();
        if (selection && selection.toString().trim().length > 0) {
            return;
        }

        const card = ev.target.closest(".oe_product_cart");
        if (!card) {
            return;
        }
        const productUrl = getCardPrimaryProductUrl(card);
        if (!productUrl) {
            return;
        }

        if (ev.type === "auxclick") {
            ev.preventDefault();
        }
        window.open(productUrl, "_blank", "noopener,noreferrer");
    }
}

registry
    .category("public.interactions")
    .add("custom_store.product_new_tab", ProductNewTab);
