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
from odoo.tools import float_compare, float_round
from odoo.tools.misc import formatLang


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ------------------------------------------------------------------
    # What the customer is buying
    # ------------------------------------------------------------------
    def _fsb_goods_lines(self):
        """The lines the bar is allowed to count.

        ``_is_delivery`` is the hook ``sale`` itself defines and ``delivery``
        overrides, so it answers on every series from 13.0 on. Notes and
        sections are skipped as well: they carry no goods and no price.
        """
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: not line.display_type and not line._is_delivery())

    def _fsb_amount(self):
        """The goods total on the basis the website chose."""
        self.ensure_one()
        field_name = ("price_total" if self.website_id.fsb_amount_basis == "total"
                      else "price_subtotal")
        return sum(self._fsb_goods_lines().mapped(field_name))

    def _fsb_threshold(self):
        """The threshold, expressed in the currency the cart is priced in."""
        self.ensure_one()
        threshold = self.website_id.fsb_free_shipping_threshold or 0.0
        source = self.website_id._fsb_currency()
        target = self.currency_id
        if source and target and source != target:
            try:
                threshold = source._convert(
                    threshold, target, self.company_id,
                    fields.Date.context_today(self))
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
    def _fsb_progress(self):
        """The bar's state, or an empty dict when there is nothing to say.

        Returning one dictionary -- instead of letting the template compare
        amounts itself -- keeps the "is it visible at all" decision in one
        place: the model tests can then state the six rules (delivery, empty
        cart, at the threshold, a cent below, threshold zero, switch off)
        without rendering a page.
        """
        self.ensure_one()
        if self.state != "draft" or not self.website_id:
            return {}
        website = self.website_id
        if not website.fsb_free_shipping_enabled:
            return {}
        currency = self.currency_id
        if not currency:
            return {}
        threshold = self._fsb_threshold()
        if float_compare(threshold, 0.0,
                         precision_rounding=currency.rounding) <= 0:
            return {}
        if not self._fsb_goods_lines():
            return {}
        amount = self._fsb_amount()
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
