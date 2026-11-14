from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    x_packing_status = fields.Selection(
        selection=[
            ("pending", "Pending QC & Pack"),
            ("qc_passed", "QC Verified"),
            ("packed", "Packed & Labelled"),
            ("handed_to_courier", "Handed to Courier"),
            ("rto_received", "RTO Received"),
        ],
        string="Packing Status",
        default="pending",
        tracking=True,
    )
    x_qc_verified = fields.Boolean(
        string="Quality Checked",
        default=False,
        help="Confirm size, stitching, and garment tag match before dispatch.",
    )
    x_dispatch_note = fields.Char(
        string="Courier / Dispatch Note",
        help="Optional Shiprocket/Delhivery pickup or packaging note.",
    )

