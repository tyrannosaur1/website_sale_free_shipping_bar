# -*- coding: utf-8 -*-
"""The six rules, stated on the model rather than read off a page.

The page tests prove the bar reaches the customer; they cannot say why it is
there or why it is missing, and a template that compares two floats itself
would look right in the source. The thresholds here are deliberately round and
deliberately awkward: 100.00 exactly, 99.99 one cent below, and 0 for the
switch that means "say nothing".
"""
from odoo.tests.common import TransactionCase


class FreeShippingAmountCase(TransactionCase):
    def setUp(self):
        super(FreeShippingAmountCase, self).setUp()
        # Up to 12.0 the module's tests only run when demo data is loaded, and
        # the demo shop sells from a public pricelist in another currency.
        # Pinning the website pricelist to the company's currency keeps the
        # figures below what the module is about: 30.00 stays 30.00.
        self.pricelist = self.env["product.pricelist"].create({
            "name": "Shop Pricelist",
            "currency_id": self.env.user.company_id.currency_id.id,
        })
        self.patch(type(self.env["website"]), "get_current_pricelist",
                   lambda website: self.env["product.pricelist"])
        self.website = self.env["website"].search([], limit=1)
        self.website.write({
            "fsb_free_shipping_enabled": True,
            "fsb_free_shipping_threshold": 100.0,
            "fsb_amount_basis": "untaxed",
        })
        self.partner = self.env["res.partner"].create({"name": "Shop Customer"})
        self.product = self.env["product.product"].create({
            "name": "Walnuts", "type": "consu", "sale_ok": True,
            "list_price": 30.0, "taxes_id": [(5, 0, 0)],
        })
        self.delivery_product = self.env["product.product"].create({
            "name": "Delivery", "type": "service", "sale_ok": True,
            "list_price": 12.0, "taxes_id": [(5, 0, 0)],
        })
        self.carrier = self.env["delivery.carrier"].create({
            "name": "Post", "delivery_type": "fixed", "fixed_price": 12.0,
            "product_id": self.delivery_product.id,
        })

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    def _order(self):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "website_id": self.website.id,
            # 12.0 takes the order pricelist from the partner, and the demo
            # public user carries one in another currency; the fixture states
            # the one the website was pinned to.
            "pricelist_id": self.pricelist.id,
        })

    def _line(self, order, price, quantity=1.0, product=None, delivery=False):
        values = {
            "order_id": order.id,
            "product_id": (product or self.product).id,
            "product_uom_qty": quantity,
            "price_unit": price,
        }
        if delivery:
            # Up to 12.0 there is no ``is_delivery`` field: the line is told apart by the
            # carrier product, which is what this series has instead.
            values["name"] = "Delivery"
        return self.env["sale.order.line"].create(values)

    def _order_with(self, price, quantity=1.0, delivery_price=0.0):
        order = self._order()
        self._line(order, price, quantity)
        if delivery_price:
            order.carrier_id = self.carrier
            self._line(order, delivery_price, product=self.delivery_product,
                       delivery=True)
            order.invalidate_cache()
        return order

    # ------------------------------------------------------------------
    # What counts
    # ------------------------------------------------------------------
    def test_the_amount_leaves_the_delivery_line_out(self):
        order = self._order_with(30.0, quantity=2, delivery_price=12.0)
        progress = order._fsb_progress(self.website)
        self.assertTrue(progress)
        self.assertEqual(progress["amount"], 60.0)
        self.assertEqual(progress["remaining"], 40.0)
        self.assertFalse(progress["reached"])

    def test_a_delivery_line_alone_claims_no_progress(self):
        """Delivery is not a purchase: the bar must not fill on it."""
        order = self._order()
        order.carrier_id = self.carrier
        self._line(order, 12.0, product=self.delivery_product, delivery=True)
        self.assertFalse(order._fsb_progress(self.website))

    def test_an_empty_cart_has_no_bar(self):
        self.assertFalse(self._order()._fsb_progress(self.website))

    # ------------------------------------------------------------------
    # The two sides of the threshold
    # ------------------------------------------------------------------
    def test_exactly_at_the_threshold_is_free_delivery(self):
        progress = self._order_with(100.0)._fsb_progress(self.website)
        self.assertTrue(progress["reached"])
        self.assertEqual(progress["percent"], 100)
        self.assertEqual(progress["remaining"], 0.0)
        self.assertNotIn("100", progress["label"])
        self.assertIn("free delivery", progress["label"])

    def test_one_cent_below_the_threshold_asks_for_one_cent(self):
        order = self._order_with(99.99)
        progress = order._fsb_progress(self.website)
        self.assertFalse(progress["reached"])
        self.assertEqual(progress["remaining"], 0.01)
        # The sentence carries the amount that is missing, not the threshold.
        self.assertIn("0.01", progress["label"])
        self.assertIn("more for free delivery", progress["label"])

    def test_the_bar_is_proportional_below_the_threshold(self):
        progress = self._order_with(25.0)._fsb_progress(self.website)
        self.assertEqual(progress["percent"], 25)

    # ------------------------------------------------------------------
    # The two switches
    # ------------------------------------------------------------------
    def test_a_zero_threshold_hides_the_bar(self):
        self.website.fsb_free_shipping_threshold = 0.0
        self.assertFalse(self._order_with(30.0)._fsb_progress(self.website))

    def test_a_negative_threshold_hides_the_bar(self):
        self.website.fsb_free_shipping_threshold = -10.0
        self.assertFalse(self._order_with(30.0)._fsb_progress(self.website))

    def test_switching_the_bar_off_hides_it(self):
        self.website.fsb_free_shipping_enabled = False
        self.assertFalse(self._order_with(30.0)._fsb_progress(self.website))

    def test_a_confirmed_order_has_no_bar(self):
        order = self._order_with(30.0)
        order.state = "sale"
        self.assertFalse(order._fsb_progress(self.website))

    # ------------------------------------------------------------------
    # The optional second setting
    # ------------------------------------------------------------------
    def test_the_comparison_can_use_the_taxed_total(self):
        tax_group = self.env["account.tax.group"].create({"name": "Taxes"})
        values = {
            "name": "VAT 10%", "amount": 10.0, "amount_type": "percent",
            "type_tax_use": "sale", "tax_group_id": tax_group.id,
        }
        if "country_id" in self.env["account.tax"]._fields:
            # Required from 15.0 on, absent before.
            values["country_id"] = self.env.ref("base.us").id
        tax = self.env["account.tax"].create(values)
        product = self.env["product.product"].create({
            "name": "Taxed Walnuts", "type": "consu", "sale_ok": True,
            "list_price": 95.0, "taxes_id": [(6, 0, tax.ids)],
        })
        order = self._order()
        line = self._line(order, 95.0, product=product)
        # Up to 15.0 the line does not take its taxes from the product on
        # create, so the fixture states them; the arithmetic under test is the
        # same either way.
        line.tax_id = [(6, 0, tax.ids)]
        # 95.00 untaxed is short of 100; 104.50 taxed is past it.
        self.assertFalse(order._fsb_progress(self.website)["reached"])
        self.website.fsb_amount_basis = "total"
        progress = order._fsb_progress(self.website)
        self.assertTrue(progress["reached"])
        self.assertAlmostEqual(progress["amount"], 104.5, places=2)

    # ------------------------------------------------------------------
    # Currency
    # ------------------------------------------------------------------
    def test_the_sentence_speaks_the_cart_currency(self):
        """Not the company's: a cart priced in another currency says so.

        The two sides are pinned rather than assumed. Up to 15.0 the website
        currency is the public pricelist's, and a database installed without
        demo data has none, so the website speaks the company's; the cart is
        then put in the other of the two currencies the test database always
        has, at a rate of two. A test that spells "USD" and "EUR" instead
        breaks on the database whose company currency is the other one.
        """
        website_currency = self.website._fsb_currency()
        other = self.env.ref("base.EUR")
        if other == website_currency:
            other = self.env.ref("base.USD")
        other.active = True
        other.active = True
        # Both sides are pinned. The demo database ships rates for these
        # currencies -- the company's included -- some of them dated after
        # 2020, and any of those would win over the pair written here: the
        # conversion would then use a rate nobody in this test chose.
        rates = self.env["res.currency.rate"]
        rates.search(
            [("currency_id", "in", (website_currency | other).ids)]).unlink()
        rates.create({
            "currency_id": website_currency.id, "rate": 1.0,
            "name": "2020-01-01",
        })
        rates.create({
            "currency_id": other.id, "rate": 2.0, "name": "2020-01-01",
        })
        pricelist = self.env["product.pricelist"].create({
            "name": "Cart Shop", "currency_id": other.id,
        })
        order = self._order_with(40.0)
        order.pricelist_id = pricelist
        order.invalidate_cache()
        progress = order._fsb_progress(self.website)
        self.assertEqual(progress["currency"], other)
        # 100.00 of the website currency is 200.00 of the cart's, 40.00 of which
        # is already in the cart.
        self.assertEqual(progress["threshold"], 200.0)
        self.assertIn("160.00", progress["label"])
        self.assertIn(other.symbol, progress["label"])
