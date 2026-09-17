# GST / Tax System Documentation

## Overview

The e-commerce website supports a centralized GST system for product pricing, cart totals, checkout totals, order snapshots, invoice/order summary, and admin management.

GST calculation is handled centrally in:

```text
shop/tax.py
```

Main functions:

```python
calculate_tax()
calculate_cart_totals()
calculate_order_totals()
calculate_shipping()
```

This avoids duplicate GST logic across cart, checkout, orders, invoices, and admin views.

## Admin GST Configuration

Admin can manage GST from:

```text
Admin Panel -> Settings -> GST Configuration
```

Available settings:

- Enable / disable GST
- Seller state
- Default GST rate
- GST pricing mode:
  - Inclusive
  - Exclusive
- Seller name
- Seller GSTIN
- Seller invoice address

GST rates can be managed dynamically:

- 0%
- 5%
- 12%
- 18%
- 28%
- Custom rates

API endpoints:

```text
GET/POST    /api/gst-rates/
GET/PATCH   /api/gst-rates/<id>/
GET/PATCH   /api/gst-config/
```

## Product GST Fields

Each product supports:

- GST applicability
- GST rate override
- GST pricing mode
- HSN/SAC code

If product GST rate is empty, the system uses:

1. Category GST rate
2. Default GST rate from GST configuration

## Category GST

Categories can have a GST rate assigned.

Products under that category inherit the category GST rate unless the product has its own GST override.

## Pricing Modes

### GST Exclusive

Example:

```text
Product Price: Rs. 1000
GST: 18%

Taxable Amount: Rs. 1000
GST Amount: Rs. 180
Final Amount: Rs. 1180
```

### GST Inclusive

Example:

```text
Display Price: Rs. 1000
GST: 18%

Taxable Amount: Rs. 847.46
GST Amount: Rs. 152.54
Final Amount: Rs. 1000
```

## CGST / SGST / IGST Logic

The system compares:

```text
Seller State
Customer Shipping/Billing State
```

If both states match:

```text
CGST = GST / 2
SGST = GST / 2
```

If states are different:

```text
IGST = full GST
```

Example intra-state:

```text
Seller State: Tamil Nadu
Customer State: Tamil Nadu
GST: 18%

CGST: 9%
SGST: 9%
```

Example inter-state:

```text
Seller State: Tamil Nadu
Customer State: Kerala
GST: 18%

IGST: 18%
```

## Discount Handling

Discounts are applied before GST.

Flow:

```text
Product subtotal
- Coupon discount
= Discounted taxable base
+ GST
+ Shipping
= Grand total
```

For multiple products, coupon discount is prorated across line items before calculating GST.

## Order Snapshot Storage

GST values are stored at the time of order creation.

This prevents old orders from changing if the admin updates GST rates later.

Stored on `Order`:

- Taxable amount
- GST amount
- CGST amount
- SGST amount
- IGST amount
- Tax type
- GST enabled snapshot
- Seller state snapshot

Stored on `OrderItem`:

- Product price
- Quantity
- Taxable amount
- GST percentage
- GST amount
- CGST amount
- SGST amount
- IGST amount
- HSN/SAC code
- Final amount

## Customer UI Behavior

When GST is enabled:

- Cart shows GST breakdown.
- Checkout shows taxable amount, CGST/SGST/IGST, shipping, and grand total.
- Order success page shows invoice-style GST details.

When GST is disabled:

- GST details are hidden from customer cart.
- GST details are hidden from checkout.
- GST details are hidden from order success/invoice page for orders created while GST was disabled.
- Emails do not show GST details.

## Files Modified

Main backend:

```text
shop/models.py
shop/tax.py
shop/views.py
shop/serializers.py
shop/api_views.py
shop/api_urls.py
shop/admin.py
shop/admin_views.py
```

Migration:

```text
shop/migrations/0032_gstrate_order_cgst_amount_order_gst_amount_and_more.py
```

Admin templates:

```text
templates/adminpanel/settings.html
templates/adminpanel/add_product.html
templates/adminpanel/edit_product.html
templates/adminpanel/categories.html
templates/adminpanel/orders.html
```

Customer templates:

```text
templates/shop/cart.html
templates/shop/checkout.html
templates/shop/order_success.html
```

Tests:

```text
shop/tests.py
```

## Test Cases Covered

GST tests cover:

1. Exclusive GST calculation
2. Inclusive GST calculation
3. Inter-state IGST calculation
4. Discount-before-GST cart calculation
5. Decimal-safe totals

Run:

```bash
python manage.py test shop.tests.GSTCalculationTests --keepdb
```

Also verified:

```bash
python manage.py check
```

## Important Notes

- GST rates are not hard-coded in calculation logic.
- Admin can update GST rates without code changes.
- Historical order GST values remain accurate.
- GST visibility follows the GST enabled setting.
- Email template currently does not include GST details.
