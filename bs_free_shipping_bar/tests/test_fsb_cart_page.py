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

Two things are different here, and both come from the series rather than from
the module. 11.0 has no ``make_jsonrpc_request`` on the test case, so the
envelope is written by hand; and it answers HTTP requests in a transaction of
their own, so the fixture -- the product, the threshold -- has to be committed
before the shop can see it. The database is the throwaway one of this run.

The checkout step is not asserted here either: 11.0 sends a cart with no
customer to the address form, which carries no total and therefore no bar.

The figures are not pinned here, only the states. The demo shop that 11.0
needs in order to run a module's tests at all sells from a pricelist in another
currency, so "70.00" is not what the shopper reads on this database; the model
tests state every amount on a cart whose pricelist the fixture owns.
"""
import json

from odoo.tests.common import HOST, PORT, HttpCase


class FreeShippingBarPageCase(HttpCase):
    def setUp(self):
        super().setUp()
        self.product = self.env["product.template"].create({
            "name": "Walnuts",
            "type": "consu",
            "sale_ok": True,
            "list_price": 30.0,
            "taxes_id": [(5, 0, 0)],
            "website_published": True,
        })
        self.variant = self.product.product_variant_id
        self._configure()

    def _configure(self, **values):
        """Set the shop's terms and make them visible to the request."""
        settings = {
            "fsb_free_shipping_enabled": True,
            "fsb_free_shipping_threshold": 100.0,
            "fsb_amount_basis": "untaxed",
        }
        settings.update(values)
        # Every test starts from an empty shop: a cart committed by an earlier
        # test is still the public user's cart, and the shop would add to it.
        self.env["sale.order"].search([("state", "=", "draft")]).write({
            "state": "cancel"})
        website = self.env["website"].search([], limit=1)
        website.write(settings)
        self.env.cr.commit()
        return website

    # ------------------------------------------------------------------
    # Filling the cart the way the shop does
    # ------------------------------------------------------------------
    def _json(self, url, values):
        """Post a JSON-RPC envelope; 11.0 has no ``make_jsonrpc_request``.

        ``url_open`` hands its payload to ``requests`` without a content type,
        and the shop's JSON route answers 400 to anything not announced as
        JSON, so the header is set on the session's own opener.
        """
        body = json.dumps({"jsonrpc": "2.0", "method": "call", "params": values})
        response = self.opener.post(
            "http://%s:%s%s" % (HOST, PORT, url),
            data=body.encode(), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text[:400])
        payload = response.json()
        self.assertNotIn("error", payload, payload.get("error"))
        return payload.get("result") or {}

    def _add(self, quantity):
        self._json("/shop/cart/update_json", {
            "product_id": self.variant.id,
            "add_qty": quantity,
        })
        self.env.cache.invalidate()
        # 11.0 has no ``website_id`` on the order: the shop keeps the site in
        # the request, so the cart just filled is the newest draft.
        return self.env["sale.order"].search(
            [("state", "=", "draft")], order="id desc", limit=1)

    def _set_quantity(self, line, quantity):
        return self._json("/shop/cart/update_json", {
            "line_id": line.id,
            "product_id": self.variant.id,
            "set_qty": quantity,
        })

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
        self.assertIn('data-fsb-reached="0"', page)
        self.assertNotIn("You have free delivery", page)

    def test_the_bar_carries_a_share_of_the_threshold(self):
        self._add(1)
        page = self._cart_page()
        self.assertIn('data-fsb-percent="', page)
        self.assertIn("width: ", page)

    def test_an_empty_cart_says_nothing_about_delivery(self):
        page = self._cart_page()
        self.assertNotIn("o_fsb_bar", page)
        self.assertNotIn("more for free delivery", page)

    # ------------------------------------------------------------------
    # Negative controls
    # ------------------------------------------------------------------
    def test_a_cart_above_the_threshold_is_not_asked_for_more(self):
        self._configure(fsb_free_shipping_threshold=1.0)
        self._add(4)
        page = self._cart_page()
        self.assertIn("o_fsb_bar", page)
        self.assertIn("You have free delivery", page)
        self.assertNotIn("more for free delivery", page)
        self.assertIn('data-fsb-reached="1"', page)
        self.assertIn("width: 100%;", page)

    def test_a_website_with_the_feature_off_prints_no_sentence(self):
        self._configure(fsb_free_shipping_enabled=False)
        self._add(1)
        page = self._cart_page()
        self.assertNotIn("o_fsb_bar", page)
        self.assertNotIn("more for free delivery", page)

    def test_a_zero_threshold_prints_no_sentence(self):
        self._configure(fsb_free_shipping_threshold=0.0)
        self._add(1)
        page = self._cart_page()
        self.assertNotIn("more for free delivery", page)

    # ------------------------------------------------------------------
    # Where the bar sits
    # ------------------------------------------------------------------
    def test_the_bar_sits_above_the_total(self):
        """Inside the block that carries the total, and before it."""
        self._add(1)
        page = self._cart_page()
        self.assertLess(page.index('id="cart_total"'), page.index("o_fsb_bar"))
        self.assertLess(page.index("o_fsb_bar"), page.index("order_total_untaxed"))

    # ------------------------------------------------------------------
    # The AJAX path
    # ------------------------------------------------------------------
    def test_a_quantity_change_past_the_threshold_drops_the_sentence(self):
        self._configure(fsb_free_shipping_threshold=1.0)
        order = self._add(1)
        line = order.order_line[:1]
        self._set_quantity(line, 4)
        page = self._cart_page()
        self.assertIn("You have free delivery", page)
        self.assertNotIn("more for free delivery", page)
