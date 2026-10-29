# -*- coding: utf-8 -*-
"""The arithmetic behind the bar, kept away from the template.

Three ideas do the work, and each of them has a wrong version that looks
plausible:

* **Only goods count.** A delivery line is what the carrier charges, not what
  the customer is buying, so it is skipped. A cart that holds nothing but a
  delivery line has bought nothing and therefore claims no progress -- the bar
  is not shown at all rather than shown at 100%.

* **Money is compared on the currency's grid.** ``amount >= threshold`` on
  floats is how a shop ends up one ten-thousandth of a cent short of the
  threshold it printed as reached. ``float_compare`` with the currency's
  rounding settles the two cents question, and the remaining amount is rounded
  to the same grid before it is spoken out loud.

* **The threshold is the website's, the sentence is the cart's.** A merchant
  types the threshold in the currency the website sells in. A pricelist may
  sell in another one; the threshold is then converted, so the customer is
  never told to add an amount in a currency they are not paying in.
"""
from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import float_compare, float_round
from odoo.tools.misc import formatLang


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ------------------------------------------------------------------
    # Which website the cart belongs to
    # ------------------------------------------------------------------
    def _fsb_website(self, website=None):
        """The website this cart is being read for.

        Up to 11.0 the order carries no ``website_id``: the shop keeps the
        website in the request, and the same cart is a cart of whichever site
        the visitor is on. A caller that has no request -- a model test, a
        nightly job -- passes the website in, which is why the whole reading
        below takes it as an argument.
        """
        self.ensure_one()
        if website:
            return website
        try:
            return request.website
        except RuntimeError:
            # No request is bound to this thread: the caller wanted a reading
            # about a website it did not name, and there is nothing to guess.
            return self.env["website"]

    # ------------------------------------------------------------------
    # What the customer is buying
    # ------------------------------------------------------------------
    def _fsb_is_delivery(self, line):
        """Whether *line* is the carrier's charge rather than goods.

        Up to 12.0 there is no ``is_delivery`` flag to read, so the only thing
        that names a delivery line is its product: the one the carrier bills
        with. A line for that product typed by hand is read as delivery too --
        a weaker rule than the flag 13.0 introduced, and the README says so.
        """
        self.ensure_one()
        carrier_product = self.carrier_id.product_id
        return bool(carrier_product) and line.product_id == carrier_product

    def _fsb_goods_lines(self):
        """The lines the bar is allowed to count.

        Notes and sections carry no goods and no price, so they are skipped
        where the series has them at all: ``display_type`` is not on every
        line before 12.0.
        """
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: not getattr(line, "display_type", False)
            and not self._fsb_is_delivery(line))

    def _fsb_amount(self, website):
        """The goods total on the basis the website chose."""
        self.ensure_one()
        field_name = ("price_total" if website.fsb_amount_basis == "total"
                      else "price_subtotal")
        return sum(self._fsb_goods_lines().mapped(field_name))

    def _fsb_threshold(self, website):
        """The threshold, expressed in the currency the cart is priced in.

        11.0 has no ``_convert``: the conversion is ``compute``, which reads
        the rate in force today rather than the one on a given date. A cart
        that lives across a rate change therefore uses the newer rate -- the
        README says so, and the sentence still speaks the cart's currency.
        """
        self.ensure_one()
        threshold = website.fsb_free_shipping_threshold or 0.0
        source = website._fsb_currency()
        target = self.currency_id
        if source and target and source != target:
            try:
                threshold = source.compute(threshold, target)
            except (ZeroDivisionError, UserError):
                # A currency that has no rate configured yet has nothing to
                # convert with. Saying the amount as written is better than
                # failing the cart page of a shop that has not finished
                # entering its rates.
                pass
        return threshold

    # ------------------------------------------------------------------
    # What the bar says
    # ------------------------------------------------------------------
    def _fsb_progress(self, website=None):
        """The bar's state, or an empty dict when there is nothing to say.

        Returning one dictionary -- instead of letting the template compare
        amounts itself -- keeps the "is it visible at all" decision in one
        place: the model tests can then state the six rules (delivery, empty
        cart, at the threshold, a cent below, threshold zero, switch off)
        without rendering a page.
        """
        self.ensure_one()
        if self.state != "draft":
            return {}
        website = self._fsb_website(website)
        if not website:
            return {}
        if not website.fsb_free_shipping_enabled:
            return {}
        currency = self.currency_id
        if not currency:
            return {}
        threshold = self._fsb_threshold(website)
        if float_compare(threshold, 0.0,
                         precision_rounding=currency.rounding) <= 0:
            return {}
        if not self._fsb_goods_lines():
            return {}
        amount = self._fsb_amount(website)
        reached = float_compare(
            amount, threshold, precision_rounding=currency.rounding) >= 0
        if reached:
            remaining = 0.0
            percent = 100
            label = _("You have free delivery")
        else:
            remaining = float_round(
                threshold - amount, precision_rounding=currency.rounding)
            # Proportional, and never 100% before the threshold is actually
            # reached: a full bar that still asks for money reads as a bug.
            percent = max(0, min(99, int(amount * 100.0 / threshold)))
            label = _("Add %(amount)s more for free delivery") % {
                "amount": formatLang(
                    self.env, remaining, currency_obj=currency)}
        return {
            "visible": True,
            "reached": reached,
            "amount": amount,
            "threshold": threshold,
            "remaining": remaining,
            "percent": percent,
            "currency": currency,
            "label": label,
        }
