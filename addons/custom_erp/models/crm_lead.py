from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    x_inquiry_channel = fields.Selection(
        selection=[
            ("website", "Website Inquiry"),
            ("instagram", "Instagram DM / Reel"),
            ("whatsapp", "WhatsApp Business"),
            ("marketplace", "Marketplace Query"),
            ("b2b_wholesale", "B2B / Boutique Wholesale"),
            ("referral", "Customer Referral"),
        ],
        string="Inquiry Channel",
        default="whatsapp",
        tracking=True,
    )
    x_product_interest = fields.Selection(
        selection=[
            ("ladies", "Ladies Wear (Kurtis / Sarees / Sets)"),
            ("men", "Men's Wear"),
            ("kids", "Kids' Wear"),
            ("fabrics", "Unstitched Fabrics"),
            ("footwear_acc", "Footwear & Accessories"),
            ("mixed", "Multi-Category / Bulk"),
        ],
        string="Category Interest",
        default="ladies",
    )
    x_preferred_size = fields.Char(
        string="Preferred Size / Fit Notes",
        help="Customer bust/size preference or custom boutique inquiry notes.",
    )

