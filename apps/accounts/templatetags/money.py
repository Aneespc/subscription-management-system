from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings

register = template.Library()


def indian_group(value):
    quantized = Decimal(value).quantize(Decimal("0.01"))
    sign = "-" if quantized < 0 else ""
    whole, _, fraction = f"{abs(quantized):.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{sign}{whole}.{fraction}"


@register.filter
def money(value):
    try:
        formatted = indian_group(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return value
    symbol = getattr(settings, "CURRENCY_SYMBOL", "₹")
    if formatted.startswith("-"):
        return f"-{symbol}{formatted[1:]}"
    return f"{symbol}{formatted}"


@register.simple_tag
def currency_symbol():
    return getattr(settings, "CURRENCY_SYMBOL", "₹")
