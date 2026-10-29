# Free Delivery Progress Bar

Tell the shopper how much is left before delivery is free: a bar in the cart and at checkout, fed by the goods in the cart only.

Odoo 10.0 – 20.0. Each series has its own branch; this one carries the 15.0 tree.

## What it does

- A threshold per website, in the website's currency, with an on/off switch.
- Below it: "Add X more for free delivery", and a bar filled in proportion.
- At or above it: "You have free delivery", a full bar, and no amount mentioned.
- The bar sits above the order total, in the cart and on every checkout step that shows the summary.
- Delivery lines never count. A cart holding only a delivery line claims no progress.
- The amount is spoken in the cart's currency, not the company's: a EUR pricelist gets a EUR sentence.
- A quantity change in the cart redraws the summary, and the bar with it, so it is never stale.
- Nothing is printed when the threshold is zero, when the switch is off, or when the cart is empty.

## Install

1. Copy the module into your addons path.
2. Update the app list, install **Free Delivery Progress Bar**.
3. Website › Configuration › Settings › **Free Delivery**: switch the bar on, set the threshold, choose whether the goods total is read tax excluded or tax included.

The threshold is the only number the merchant types. It is compared with the goods in the cart on the currency's rounding grid, so a cent short is a cent short and a cent over is free.

## What it does not do

- It does not create or price a delivery method. The carrier's own rates and its "free shipping from" note stay where they are; this module only reports progress towards the threshold.
- It does not touch carts in the backend. The bar belongs to the website.

## Notes for this series

- Depends on `delivery` as well as `website_sale`: up to 15.0 the delivery line is the one the carrier module flags, and without that module there is nothing to flag.
- 15.0 has no `t-out`; the sentence is escaped with `t-esc`, the directive it replaced.
- The AJAX fragment the cart re-renders is `website_sale.short_cart_summary`, which is where the bar ends up being carried.

## License

OPL-1. See `LICENSE`.

## Support

Open an issue on this repository.
