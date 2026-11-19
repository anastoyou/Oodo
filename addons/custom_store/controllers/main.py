import json
from pathlib import Path

from odoo import http
from odoo.addons.website_sale.controllers.main import WebsiteSale


class CustomStoreWebsiteSale(WebsiteSale):
    """Extension controller for custom storefront and per-(website, product) custom PDPs."""

    @http.route()
    def product(self, product, pricelist=None, **kwargs):
        res = super().product(product, pricelist=pricelist, **kwargs)
        if getattr(res, "template", None) != "website_sale.product":
            return res

        website = self.env.website
        custom_pdp = (
            self.env["custom.store.product.pdp"]
            .sudo()
            .search(
                [
                    ("website_id", "=", website.id),
                    ("product_tmpl_id", "=", product.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
        )
        if not custom_pdp:
            return res

        if custom_pdp.mode == "native" and custom_pdp.template_key:
            has_view = (
                self.env["ir.ui.view"]
                .sudo()
                .search_count(
                    [
                        ("key", "=", custom_pdp.template_key),
                        ("website_id", "in", (False, website.id)),
                        ("active", "=", True),
                    ]
                )
            )
            if has_view:
                res.qcontext["custom_pdp"] = custom_pdp
                res.template = custom_pdp.template_key
        elif custom_pdp.mode == "react" and custom_pdp.bundle_js:
            # Developer full-data preview (?pdp_dev=full) is strictly restricted to internal editors.
            is_editor = self.env.user.has_group("website.group_website_restricted_editor")
            use_dev_full = (
                kwargs.get("pdp_dev") == "full"
                and is_editor
                and bool(custom_pdp.bundle_full_js)
            )
            target_js = custom_pdp.bundle_full_js if use_dev_full else custom_pdp.bundle_js
            target_css = (
                (custom_pdp.bundle_full_css or custom_pdp.bundle_css)
                if use_dev_full
                else custom_pdp.bundle_css
            )

            res.qcontext["custom_pdp"] = custom_pdp
            res.qcontext["pdp_bundle_js_url"] = self._versioned_bundle_url(target_js)
            res.qcontext["pdp_bundle_css_url"] = (
                self._versioned_bundle_url(target_css) if target_css else ""
            )
            res.qcontext["pdp_bootstrap_json"] = json.dumps(
                self._build_react_pdp_payload(product, res.qcontext)
            )
            res.template = "custom_store.react_pdp_shell"

        return res

    @staticmethod
    def _versioned_bundle_url(url_path):
        """Append file mtime query string so rebuilt Vite bundles bypass browser cache."""
        if not url_path:
            return ""
        rel = url_path.lstrip("/")
        addons_root = Path(__file__).resolve().parents[2]
        disk_path = (addons_root / rel).resolve()
        if addons_root in disk_path.parents and disk_path.is_file():
            return f"{url_path}?v={int(disk_path.stat().st_mtime)}"
        return url_path

    def _prepare_product_values(self, product, **kwargs):
        """Extend QWeb context available on product detail pages (/shop/<product>)."""
        values = super()._prepare_product_values(product, **kwargs)
        return values

    def _serialize_combination_info(self, combination_info):
        """Extract JSON-safe combination fields from _get_combination_info output."""
        skip_keys = {
            "product_taxes",
            "taxes",
            "currency",
            "combination",
            "discount_start_date",
            "discount_end_date",
        }
        payload = {}
        for key, value in combination_info.items():
            if key in skip_keys:
                continue
            if hasattr(value, "ids"):
                payload[key] = value.ids
            elif isinstance(value, (str, int, float, bool)) or value is None:
                payload[key] = value
            elif isinstance(value, (list, dict)):
                payload[key] = value
            else:
                payload[key] = str(value)

        combination = combination_info.get("combination")
        payload["combination_ptav_ids"] = combination.ids if combination else []
        currency = combination_info.get("currency")
        if currency:
            payload["currency_precision"] = currency.decimal_places
        return payload

    def _serialize_related_templates(self, templates):
        return [
            {
                "id": tmpl.id,
                "product_tmpl_id": tmpl.id,
                "name": tmpl.name,
                "website_url": tmpl.website_url,
                "image_url": f"/web/image/product.template/{tmpl.id}/image_512",
                "price": float(tmpl._get_combination_info().get("price") or 0.0),
            }
            for tmpl in templates
        ]

    def _serialize_related_variants(self, variants):
        return [
            {
                "id": var.id,
                "product_tmpl_id": var.product_tmpl_id.id,
                "name": var.display_name,
                "website_url": var.website_url,
                "image_url": f"/web/image/product.product/{var.id}/image_512",
                "price": float(var._get_combination_info_variant().get("price") or 0.0),
            }
            for var in variants
        ]

    def _build_react_pdp_payload(self, product, qcontext):
        """Build JSON bootstrap data for the React + Tailwind PDP engine."""
        website = self.env.website
        product_variant = qcontext.get("product_variant")
        combination_info = qcontext.get("combination_info") or {}
        combination = combination_info.get("combination")
        selected_ptav_ids = set(combination.ids if combination else [])
        attribute_value_images = qcontext.get("attribute_value_images") or {}
        category = qcontext.get("category")

        currency = combination_info.get("currency") or website.currency_id
        fit_field = product._fields.get("x_fit_type")
        fit_labels = dict(fit_field.selection) if fit_field and fit_field.selection else {}

        images = []
        image_records = product_variant._get_images() if product_variant else product._get_images()
        for img in image_records:
            video_url = getattr(img, "video_url", False) if img._name == "product.image" else False
            embed_code = getattr(img, "embed_code", False) if img._name == "product.image" else False
            images.append(
                {
                    "id": img.id,
                    "model": img._name,
                    "name": getattr(img, "name", False) or product.name,
                    "url": f"/web/image/{img._name}/{img.id}/image_1024",
                    "thumb_url": f"/web/image/{img._name}/{img.id}/image_128",
                    "video_url": video_url or False,
                    "embed_code": str(embed_code) if embed_code else False,
                }
            )

        attribute_lines = []
        for ptal in product.valid_product_template_attribute_line_ids:
            attr = ptal.attribute_id
            ptavs = ptal.product_template_value_ids._only_active()
            values_data = []
            for ptav in ptavs:
                pav = ptav.product_attribute_value_id
                img_url = attribute_value_images.get(ptav.id)
                if not img_url and pav.image:
                    img_url = f"/web/image/product.attribute.value/{pav.id}/image"
                values_data.append(
                    {
                        "id": ptav.id,
                        "name": ptav.name,
                        "product_attribute_value_id": pav.id,
                        "html_color": ptav.html_color or pav.html_color or False,
                        "image_url": img_url or False,
                        "is_custom": bool(ptav.is_custom),
                        "price_extra": float(ptav.price_extra or 0.0),
                        "selected": ptav.id in selected_ptav_ids,
                    }
                )
            attribute_lines.append(
                {
                    "id": ptal.id,
                    "attribute_id": attr.id,
                    "attribute_name": attr.name,
                    "display_type": attr.display_type,
                    "create_variant": attr.create_variant,
                    "is_thumbnail_visible": bool(attr.is_thumbnail_visible),
                    "values": values_data,
                }
            )

        categories = []
        if category:
            for cat in category.parents_and_self:
                categories.append(
                    {
                        "id": cat.id,
                        "name": cat.name,
                        "url": cat.website_url,
                    }
                )

        tag_records = (
            product_variant.all_product_tag_ids.filtered("visible_to_customers")
            if product_variant
            else product.product_tag_ids.filtered("visible_to_customers")
        )
        tags = [
            {
                "id": tag.id,
                "name": tag.name,
                "color": tag.color,
                "image_url": f"/web/image/product.tag/{tag.id}/image" if tag.image else False,
            }
            for tag in tag_records
        ]

        ribbon_rec = product.sudo()._get_ribbon(
            price_vals=combination_info, variant=product_variant
        )
        ribbon = (
            {
                "id": ribbon_rec.id,
                "name": ribbon_rec.name,
                "bg_color": ribbon_rec.bg_color,
                "text_color": ribbon_rec.text_color,
                "position": ribbon_rec.position,
                "style": ribbon_rec.style,
            }
            if ribbon_rec
            else None
        )

        docs = product._get_product_page_documents(variant=product_variant)
        documents = [
            {
                "id": doc.id,
                "name": doc.ir_attachment_id.name or doc.name,
                "url": f"{product.website_url}/document/{doc.id}",
                "is_external": doc.ir_attachment_id.type == "url",
            }
            for doc in docs
        ]

        alt_products = self._serialize_related_templates(
            product._get_website_alternative_product()
        )
        acc_products = self._serialize_related_variants(
            product._get_website_accessory_product()
        )
        opt_products = self._serialize_related_templates(
            getattr(product, "optional_product_ids", self.env["product.template"]).filtered(
                lambda p: p.website_id.id in (False, website.id) and p.is_published
            )
        )

        wishlist_enabled = bool(
            "product.wishlist" in self.env
            and website.is_view_active("website_sale.product_add_to_wishlist")
        )
        wished_ids = (
            self.env["product.wishlist"].current().mapped("product_id").ids
            if "product.wishlist" in self.env
            else []
        )
        buy_now_enabled = bool(website.is_view_active("website_sale.product_buy_now"))
        show_quantity = bool(website.is_view_active("website_sale.product_quantity"))
        compare_enabled = bool(
            website.is_view_active("website_sale.product_add_to_compare")
            and product._can_be_added_to_comparison()
        )
        rating_enabled = bool(website.is_view_active("website_sale.product_comment"))
        tax_indication_enabled = bool(website.is_view_active("website_sale.tax_indication"))

        serialized_combo = self._serialize_combination_info(combination_info)
        if "is_in_wishlist" not in serialized_combo:
            serialized_combo["is_in_wishlist"] = bool(
                product_variant and product_variant.id in wished_ids
            )
        uoms = [
            {"id": u.id, "name": u.name}
            for u in product._get_available_uoms()
        ]

        return {
            "website": {
                "id": website.id,
                "name": website.name,
                "store_code": website.x_store_code or "",
            },
            "currency": {
                "id": currency.id,
                "name": currency.name,
                "symbol": currency.symbol,
                "position": currency.position,
                "decimal_places": currency.decimal_places,
            },
            "product": {
                "id": product.id,
                "name": product.name,
                "default_code": product.default_code or "",
                "type": product.type,
                "website_url": product.website_url,
                "description_sale": product.description_sale or "",
                "description_ecommerce": str(product.description_ecommerce or ""),
                "website_description": str(product.website_description or ""),
                "specs": {
                    "x_fabric": getattr(product, "x_fabric", False) or "",
                    "x_fit_type": getattr(product, "x_fit_type", False) or "",
                    "x_fit_type_label": fit_labels.get(getattr(product, "x_fit_type", False), ""),
                    "x_wash_care": getattr(product, "x_wash_care", False) or "",
                    "x_dispatch_days": getattr(product, "x_dispatch_days", False) or 0,
                },
                "categories": categories,
                "uoms": uoms,
                "tags": tags,
                "ribbon": ribbon,
                "documents": documents,
                "alternative_products": alt_products,
                "accessory_products": acc_products,
                "optional_products": opt_products,
                "rating": {
                    "enabled": rating_enabled,
                    "avg": float(getattr(product.sudo(), "rating_avg", 0.0) or 0.0),
                    "count": int(getattr(product.sudo(), "rating_count", 0) or 0),
                },
            },
            "combination_info": serialized_combo,
            "attribute_lines": attribute_lines,
            "attribute_exclusions": product._get_attribute_exclusions(),
            "images": images,
            "options": {
                "is_add_to_cart_possible": bool(product._has_ecommerce_sellable_variants()),
                "show_quantity": show_quantity,
                "buy_now_enabled": buy_now_enabled,
                "wishlist_enabled": wishlist_enabled,
                "compare_enabled": compare_enabled,
                "tax_indication_enabled": tax_indication_enabled,
                "wishlist_product_ids": wished_ids,
                "view_track": bool(qcontext.get("view_track")),
            },
            "user": {
                "is_public": bool(website.is_public_user()),
                "email": qcontext.get("user_email") or "",
            },
            "routes": {
                "shop": qcontext.get("shop_path") or "/shop",
                "cart": "/shop/cart",
                "checkout": "/shop/checkout",
                "cart_add": "/shop/cart/add",
                "combination_info": "/website_sale/get_combination_info",
                "create_variant": "/sale/create_product_variant",
                "wishlist_add": "/shop/wishlist/add",
                "wishlist_remove": "/shop/wishlist/remove",
                "wishlist_ids": "/shop/wishlist/get_product_ids",
                "compare": "/shop/compare",
                "stock_notify": "/shop/add/stock_notification",
                "contact_us": website._get_contact_us_url(combination_info.get("display_name", product.name)),
            },
        }
