import logging
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.discounts.models import Discount, DiscountUsage

logger = logging.getLogger(__name__)


def quantize_currency(amount):
    """Round decimal amount to 2 decimal places with ROUND_HALF_UP."""
    if amount is None:
        return Decimal("0.00")
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class DiscountService:
    @classmethod
    def get_eligible_discounts(cls, subscription=None, lines=None, subtotal=None, on_date=None):
        """
        Find all active, non-expired discounts that are under their usage limit
        and satisfy purchase/quantity/scope constraints.
        """
        if on_date is None:
            on_date = timezone.now().date()

        # Filter active and date-valid discounts
        qs = Discount.objects.filter(
            is_active=True,
            start_date__lte=on_date,
            end_date__gte=on_date,
        ).filter(
            Q(usage_limit__isnull=True) | Q(usage_count__lt=F("usage_limit"))
        ).prefetch_related("products")

        eligible = []
        lines_list = list(lines) if lines is not None else []

        # Calculate line metrics if lines provided
        total_quantity = 0
        product_ids_in_lines = set()
        calculated_subtotal = Decimal("0.00")

        for line in lines_list:
            qty = getattr(line, "quantity", 1) or 1
            total_quantity += qty
            p_id = getattr(line, "product_id", None)
            if not p_id and hasattr(line, "product") and line.product:
                p_id = line.product.id
            if p_id:
                product_ids_in_lines.add(p_id)

            amt = getattr(line, "amount", None)
            if amt is None:
                unit_price = getattr(line, "unit_price", Decimal("0.00")) or Decimal("0.00")
                amt = Decimal(qty) * Decimal(str(unit_price))
            calculated_subtotal += Decimal(str(amt))

        effective_subtotal = subtotal if subtotal is not None else calculated_subtotal

        for discount in qs:
            # Check remaining usage limit
            if discount.usage_limit is not None and discount.usage_count >= discount.usage_limit:
                continue

            # Minimum purchase condition
            if discount.minimum_purchase is not None:
                if effective_subtotal < discount.minimum_purchase:
                    continue

            # Minimum quantity condition
            if discount.minimum_quantity is not None:
                if total_quantity < discount.minimum_quantity:
                    continue

            # Scope condition: ALL, PRODUCTS, or SUBSCRIPTIONS
            if discount.applies_to == Discount.AppliesTo.ALL:
                eligible.append(discount)
            elif discount.applies_to == Discount.AppliesTo.SUBSCRIPTIONS:
                if subscription is not None:
                    eligible.append(discount)
            elif discount.applies_to == Discount.AppliesTo.PRODUCTS:
                discount_product_ids = set(discount.products.values_list("id", flat=True))
                # If matching lines exist or no lines were provided for evaluation
                if not lines_list or (discount_product_ids & product_ids_in_lines):
                    eligible.append(discount)

        return eligible

    @classmethod
    def calculate(cls, discount, lines=None, subtotal=None):
        """
        Calculates the discount amount, capped so it never exceeds the amount it applies to.
        Returns a Decimal rounded to 2 places.
        """
        lines_list = list(lines) if lines is not None else []

        # Determine the base amount the discount applies to
        if discount.applies_to == Discount.AppliesTo.PRODUCTS and lines_list:
            applicable_product_ids = set(discount.products.values_list("id", flat=True))
            applicable_amount = Decimal("0.00")
            for line in lines_list:
                p_id = getattr(line, "product_id", None)
                if not p_id and hasattr(line, "product") and line.product:
                    p_id = line.product.id
                if p_id in applicable_product_ids:
                    amt = getattr(line, "amount", None)
                    if amt is None:
                        qty = getattr(line, "quantity", 1) or 1
                        unit_p = getattr(line, "unit_price", Decimal("0.00")) or Decimal("0.00")
                        amt = Decimal(qty) * Decimal(str(unit_p))
                    applicable_amount += Decimal(str(amt))
        else:
            if subtotal is not None:
                applicable_amount = Decimal(str(subtotal))
            elif lines_list:
                applicable_amount = sum(
                    Decimal(str(getattr(l, "amount", Decimal(getattr(l, "quantity", 1)) * getattr(l, "unit_price", Decimal("0.00")))))
                    for l in lines_list
                )
            else:
                applicable_amount = Decimal("0.00")

        if applicable_amount <= Decimal("0.00"):
            return Decimal("0.00")

        if discount.discount_type == Discount.DiscountType.PERCENTAGE:
            raw_discount = applicable_amount * (discount.value / Decimal("100.00"))
        else:  # FIXED
            raw_discount = discount.value

        # Cap so discount never exceeds the applicable amount
        discount_amount = min(raw_discount, applicable_amount)
        discount_amount = max(Decimal("0.00"), discount_amount)
        return quantize_currency(discount_amount)

    @classmethod
    def apply(cls, discount, invoice, amount):
        """
        Applies a discount to an invoice concurrency-safely inside an atomic transaction.
        Locks the discount row with select_for_update, re-checks usage limit,
        creates DiscountUsage, and atomically increments usage_count using F().
        """
        from apps.invoicing.models import Invoice

        amount = quantize_currency(amount)
        if amount <= Decimal("0.00"):
            return None

        with transaction.atomic():
            # Concurrency-safe lock on the discount record
            locked_discount = Discount.objects.select_for_update().get(pk=discount.pk)

            # Re-verify active and dates
            eval_date = invoice.issue_date or timezone.now().date()
            if not locked_discount.is_active:
                raise ValidationError(f"Discount '{locked_discount.name}' is inactive.")
            if eval_date < locked_discount.start_date or eval_date > locked_discount.end_date:
                raise ValidationError(f"Discount '{locked_discount.name}' is outside its active date range.")

            # Re-verify usage limit under lock
            if locked_discount.usage_limit is not None and locked_discount.usage_count >= locked_discount.usage_limit:
                raise ValidationError(f"Discount '{locked_discount.name}' has reached its usage limit.")

            # Check if this discount is already applied to this invoice
            if DiscountUsage.objects.filter(discount=locked_discount, invoice=invoice).exists():
                raise ValidationError(f"Discount '{locked_discount.name}' is already applied to invoice {invoice.invoice_number}.")

            # Record usage
            usage = DiscountUsage.objects.create(
                discount=locked_discount,
                customer=invoice.customer,
                subscription=invoice.subscription,
                invoice=invoice,
                discount_amount=amount,
            )

            # Atomically increment usage_count with F() expression
            Discount.objects.filter(pk=locked_discount.pk).update(usage_count=F("usage_count") + 1)
            locked_discount.refresh_from_db(fields=["usage_count"])

            logger.info(
                f"Applied discount '{locked_discount.name}' (${amount}) to invoice {invoice.invoice_number}. "
                f"Usage count is now {locked_discount.usage_count}."
            )
            return usage

