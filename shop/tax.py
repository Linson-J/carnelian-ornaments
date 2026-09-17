from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .models import DeliveryConfig, GSTConfig, GSTRate, Product


TWOPLACES = Decimal('0.01')


def money(value):
    return Decimal(str(value or '0')).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def normalize_state(value):
    return (value or '').strip().casefold()


def split_tax(total_tax, is_interstate):
    total_tax = money(total_tax)
    if is_interstate:
        return money(0), money(0), total_tax
    half = money(total_tax / Decimal('2'))
    return half, money(total_tax - half), money(0)


def get_product_gst_rate(product, config=None):
    if config is None:
        config = GSTConfig.current()
    if not config.enabled or not product.gst_applicable:
        return Decimal('0.00')
    rate = product.gst_rate
    if not rate and product.category_id:
        rate = getattr(product.category, 'gst_rate', None)
    if not rate:
        rate = config.default_rate
    if not rate or not rate.is_active:
        return Decimal('0.00')
    return Decimal(rate.percentage)


def get_product_pricing_mode(product, config=None):
    if product.gst_pricing_mode:
        return product.gst_pricing_mode
    if config:
        return config.pricing_mode
    return GSTConfig.PricingMode.EXCLUSIVE


def get_sale_price(product):
    return money(product.discount_price if product.discount_price else product.price)


@dataclass
class LineInput:
    product: Product
    quantity: int


def calculate_tax(gross_amount, gst_rate, pricing_mode, discount=0, is_interstate=False):
    gross_amount = money(gross_amount)
    discount = min(money(discount), gross_amount)
    net_amount = money(gross_amount - discount)
    gst_rate = Decimal(str(gst_rate or '0'))

    if gst_rate <= 0:
        taxable = net_amount
        gst = money(0)
    elif pricing_mode == GSTConfig.PricingMode.INCLUSIVE:
        divisor = Decimal('100') + gst_rate
        taxable = money((net_amount * Decimal('100')) / divisor)
        gst = money(net_amount - taxable)
    else:
        taxable = net_amount
        gst = money(taxable * gst_rate / Decimal('100'))

    cgst, sgst, igst = split_tax(gst, is_interstate)
    final_amount = money(taxable + gst)
    return {
        'gross_amount': gross_amount,
        'discount': discount,
        'taxable_amount': taxable,
        'gst_percentage': gst_rate.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
        'gst_amount': gst,
        'cgst_amount': cgst,
        'sgst_amount': sgst,
        'igst_amount': igst,
        'final_amount': final_amount,
    }


def calculate_shipping(subtotal, matching_zone=None):
    subtotal = money(subtotal)
    config = DeliveryConfig.current()
    if subtotal >= money(config.free_threshold):
        return money(0), True
    if config.fee_type == DeliveryConfig.FeeType.ZONE and matching_zone:
        return money(matching_zone.delivery_fee), False
    if config.fee_type == DeliveryConfig.FeeType.THRESHOLD and matching_zone:
        return money(matching_zone.delivery_fee), False
    return money(config.base_fee), False


def _discount_share(line_total, subtotal, total_discount, index, line_count, allocated):
    total_discount = min(money(total_discount), money(subtotal))
    if total_discount <= 0 or subtotal <= 0:
        return money(0)
    if index == line_count - 1:
        return money(total_discount - allocated)
    return money((money(line_total) / money(subtotal)) * total_discount)


def calculate_cart_totals(cart, customer_state='', coupon_discount=0, shipping=0, include_shipping=True):
    config = GSTConfig.current()
    product_ids = []
    clean_quantities = {}
    for product_id, qty in (cart or {}).items():
        try:
            product_id_int = int(product_id)
            qty_int = int(qty)
        except (TypeError, ValueError):
            continue
        if qty_int > 0:
            product_ids.append(product_id_int)
            clean_quantities[product_id_int] = qty_int

    products = {
        product.id: product
        for product in Product.objects.filter(id__in=product_ids).select_related('category', 'gst_rate', 'category__gst_rate').prefetch_related('images')
    }

    lines = []
    subtotal = money(0)
    original_total = money(0)
    for product_id in product_ids:
        product = products.get(product_id)
        if not product:
            continue
        qty = clean_quantities[product_id]
        unit_price = get_sale_price(product)
        line_total = money(unit_price * qty)
        subtotal = money(subtotal + line_total)
        original_total = money(original_total + (money(product.price) * qty))
        lines.append({
            'product': product,
            'quantity': qty,
            'unit_price': unit_price,
            'line_total': line_total,
        })

    product_discount = money(original_total - subtotal)
    coupon_discount = min(money(coupon_discount), subtotal)
    is_interstate = bool(customer_state) and normalize_state(customer_state) != normalize_state(config.seller_state)

    allocated = money(0)
    taxed_lines = []
    totals = {
        'subtotal': subtotal,
        'original_total': original_total,
        'discount': product_discount,
        'coupon_discount': coupon_discount,
        'total_discount': money(product_discount + coupon_discount),
        'taxable_amount': money(0),
        'gst_amount': money(0),
        'cgst_amount': money(0),
        'sgst_amount': money(0),
        'igst_amount': money(0),
    }

    for index, line in enumerate(lines):
        share = _discount_share(line['line_total'], subtotal, coupon_discount, index, len(lines), allocated)
        allocated = money(allocated + share)
        product = line['product']
        tax = calculate_tax(
            gross_amount=line['line_total'],
            gst_rate=get_product_gst_rate(product, config),
            pricing_mode=get_product_pricing_mode(product, config),
            discount=share,
            is_interstate=is_interstate,
        )
        primary_image = product.images.filter(is_primary=True).first() or product.images.first()
        row = {
            **line,
            **tax,
            'image': primary_image,
            'subtotal': line['line_total'],
            'total_price': tax['final_amount'],
            'hsn_sac_code': product.hsn_sac_code,
            'gst_pricing_mode': get_product_pricing_mode(product, config),
        }
        taxed_lines.append(row)
        for key in ('taxable_amount', 'gst_amount', 'cgst_amount', 'sgst_amount', 'igst_amount'):
            totals[key] = money(totals[key] + tax[key])

    shipping = money(shipping if include_shipping else 0)
    totals['shipping'] = shipping
    totals['grand_total'] = money(totals['taxable_amount'] + totals['gst_amount'] + shipping)
    totals['tax_type'] = 'igst' if is_interstate else 'cgst_sgst'
    totals['gst_enabled'] = config.enabled
    totals['seller_state'] = config.seller_state
    totals['is_interstate'] = is_interstate
    return {'items': taxed_lines, 'totals': totals, 'config': config}


def calculate_order_totals(cart, customer_state='', coupon_discount=0, shipping=0):
    return calculate_cart_totals(
        cart=cart,
        customer_state=customer_state,
        coupon_discount=coupon_discount,
        shipping=shipping,
        include_shipping=True,
    )
