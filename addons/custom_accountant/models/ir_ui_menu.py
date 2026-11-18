from odoo import api, models


class IrUiMenuAlphabetical(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def load_menus(self, debug):
        menus = super().load_menus(debug)
        root = menus.get("root")
        if root and root.get("children"):
            sorted_children = sorted(
                root["children"],
                key=lambda mid: ((menus.get(mid) or {}).get("name") or "").lower(),
            )
            menus = {**menus, "root": {**root, "children": sorted_children}}
        return menus

    @api.model
    def load_menus_root(self):
        root = super().load_menus_root()
        if root.get("children"):
            root = {
                **root,
                "children": sorted(
                    root["children"],
                    key=lambda m: (m.get("name") or "").lower(),
                ),
            }
        return root
