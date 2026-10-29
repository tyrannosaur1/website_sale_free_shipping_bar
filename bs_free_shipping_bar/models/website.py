# -*- coding: utf-8 -*-
from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    fsb_free_shipping_enabled = fields.Boolean(
        "Free Delivery Bar",
        help="Show the progress bar towards free delivery in the cart and at "
             "checkout. Off by default: a shop that says nothing about free "
             "delivery must not start promising one.",
    )
    fsb_free_shipping_threshold = fields.Float(
        "Free Delivery Threshold",
        digits="Product Price",
        help="Amount, in the website currency, at which delivery becomes free. "
             "Zero turns the bar off, exactly like the switch above.",
    )
    fsb_amount_basis = fields.Selection(
        [("untaxed", "Goods, tax excluded"),
         ("total", "Goods, tax included")],
        "Amount Compared",
        default="untaxed",
        required=True,
        help="Which goods total the threshold is compared with. Delivery is "
             "never part of it: the bar measures what the customer is buying, "
             "not what the carrier charges.",
    )

    def _fsb_currency(self):
        """The currency the threshold is written in: the website's own.

        ``website_sale`` puts it on the website on every series up to 15.0, as
        the currency of the public pricelist, so it is read from there rather
        than from the company, which is the currency a shop with several
        pricelists does not sell in. The company's is only the fallback for a
        site whose pricelist is not set yet.
        """
        self.ensure_one()
        return self.currency_id or self.company_id.currency_id
