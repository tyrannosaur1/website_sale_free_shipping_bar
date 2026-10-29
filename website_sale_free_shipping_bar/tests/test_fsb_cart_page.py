# -*- coding: utf-8 -*-
"""The pages a shopper actually touches, fetched over HTTP.

The model tests say the arithmetic is right; they say nothing about whether the
bar is in the page, inside the card that carries the total, or in a template
that the shop never renders. So the cart is filled through the shop's own route
and the HTML that comes back is read: a bar that lives in the source but not in
the response is the failure this file exists to catch.

The two negative controls are the interesting half: a cart already above the
threshold must not be told to add anything, and a website that switched the
feature off must not print the sentence at all -- not with zero, not with an
empty amount.
"""
from odoo.tests.common import HttpCase


class FreeShippingBarPageCase(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.website.write({
            "fsb_free_shipping_enabled": True,
            "fsb_free_shipping_threshold": 100.0,
            "fsb_amount_basis": "untaxed",
        })
        cls.product = cls.env["product.template"].create({
            "name": "Walnuts",
            "type": "consu",
            "sale_ok": True,
            "list_price": 30.0,
            "taxes_id": [(5, 0, 0)],
            "website_published": True,
        })
        cls.variant = cls.product.product_variant_id

    # ------------------------------------------------------------------
    # Filling the cart the way the shop does
    # ------------------------------------------------------------------
    def _add(self, quantity):
        self.make_jsonrpc_request("/shop/cart/add", {
            "product_template_id": self.product.id,
            "product_id": self.variant.id,
            "quantity": quantity,
        })
        self.env.invalidate_all()
        return self.env["sale.order"].search(
            [("website_id", "=", self.website.id), ("state", "=", "draft")],
            order="id desc", limit=1)

    def _cart_page(self):
        response = self.url_open("/shop/cart")
        self.assertEqual(response.status_code, 200)
        return response.text

    # ------------------------------------------------------------------
    # The cart
    # ------------------------------------------------------------------
    def test_the_cart_says_what_is_still_missing(self):
        self._add(1)
        page = self._cart_page()
        self.assertIn("o_fsb_bar", page)
        self.assertIn("more for free delivery", page)
        self.assertIn("70.00", page)
        self.assertIn('data-fsb-remaining="70.0"', page)
        self.assertIn('data-fsb-reached="0"', page)
        self.assertNotIn("You have free delivery", page)

    def test_the_bar_shows_a_partial_fill(self):
        self._add(1)
        page = self._cart_page()
        # 30 of 100 is 30%.
        self.assertIn("width: 30%;", page)
        self.assertIn('data-fsb-percent="30"', page)

    def test_an_empty_cart_says_nothing_about_delivery(self):
        page = self._cart_page()
        self.assertNotIn("o_fsb_bar", page)
        self.assertNotIn("more for free delivery", page)

    # ------------------------------------------------------------------
    # Negative controls
    # ------------------------------------------------------------------
    def test_a_cart_above_the_threshold_is_not_asked_for_more(self):
        self._add(4)  # 120.00
        page = self._cart_page()
        self.assertIn("o_fsb_bar", page)
        self.assertIn("You have free delivery", page)
        self.assertNotIn("more for free delivery", page)
        self.assertIn("width: 100%;", page)

    def test_a_website_with_the_feature_off_prints_no_sentence(self):
        self.website.fsb_free_shipping_enabled = False
        self.env.flush_all()
        self._add(1)
        page = self._cart_page()
        self.assertNotIn("o_fsb_bar", page)
        self.assertNotIn("more for free delivery", page)

    def test_a_zero_threshold_prints_no_sentence(self):
        self.website.fsb_free_shipping_threshold = 0.0
        self.env.flush_all()
        self._add(1)
        page = self._cart_page()
        self.assertNotIn("more for free delivery", page)

    # ------------------------------------------------------------------
    # Checkout
    # ------------------------------------------------------------------
    def test_the_checkout_page_carries_the_bar(self):
        self._add(1)
        response = self.url_open("/shop/checkout")
        self.assertEqual(response.status_code, 200)
        self.assertIn("more for free delivery", response.text)
        self.assertIn("70.00", response.text)

    # ------------------------------------------------------------------
    # The AJAX path
    # ------------------------------------------------------------------
    def test_a_quantity_change_re_renders_the_amount(self):
        """The response the shop swaps into the page must carry the new sum.

        This is the route the cart's quantity buttons call; the fragment it
        returns replaces the summary in place, so an amount kept outside that
        fragment would keep saying 70.00 after the customer typed two.
        """
        order = self._add(1)
        line = order.order_line[:1]
        data = self.make_jsonrpc_request("/shop/cart/update", {
            "line_id": line.id,
            "product_id": self.variant.id,
            "quantity": 2,
        })
        fragment = data["website_sale.total"]
        self.assertIn("more for free delivery", fragment)
        self.assertIn("40.00", fragment)
        self.assertNotIn("70.00", fragment)

    def test_a_quantity_change_past_the_threshold_drops_the_sentence(self):
        order = self._add(1)
        line = order.order_line[:1]
        data = self.make_jsonrpc_request("/shop/cart/update", {
            "line_id": line.id,
            "product_id": self.variant.id,
            "quantity": 4,
        })
        fragment = data["website_sale.total"]
        self.assertIn("You have free delivery", fragment)
        self.assertNotIn("more for free delivery", fragment)
