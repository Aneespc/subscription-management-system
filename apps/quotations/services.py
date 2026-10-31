from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from .models import Quotation, QuotationLine, QuotationTemplate
from apps.subscriptions.models import Subscription, SubscriptionLine
from apps.plans.models import Plan


class QuotationService:
    @staticmethod
    def recalculate_totals(quotation):
        """Recalculate subtotal, tax amount, and total amount for a quotation."""
        lines = quotation.lines.all()
        subtotal = Decimal("0.00")
        tax_amount = Decimal("0.00")

        for line in lines:
            line_amount = line.unit_price * line.quantity
            line_tax = line_amount * (line.tax_rate / Decimal("100.00"))
            line.amount = line_amount
            line.save(update_fields=["amount"])
            subtotal += line_amount
            tax_amount += line_tax

        quotation.subtotal = subtotal.quantize(Decimal("0.01"))
        quotation.tax_amount = tax_amount.quantize(Decimal("0.01"))
        quotation.total_amount = (subtotal + tax_amount).quantize(Decimal("0.01"))
        quotation.save(update_fields=["subtotal", "tax_amount", "total_amount"])
        return quotation

    @staticmethod
    def create_from_template(template, customer, created_by=None, payment_terms=Quotation.PaymentTerms.NET_30):
        """Create a new quotation pre-filled from a quotation template."""
        today = timezone.now().date()
        expiry_date = today + timedelta(days=template.validity_days)

        quotation = Quotation.objects.create(
            customer=customer,
            template=template,
            created_by=created_by,
            issue_date=today,
            expiry_date=expiry_date,
            payment_terms=payment_terms,
            status=Quotation.Status.DRAFT,
            notes=f"Generated from template: {template.name}"
        )

        # Copy lines from template if any
        for t_line in template.template_lines.all():
            base_price = t_line.product.sales_price
            extra = t_line.variant.price_extra if t_line.variant else Decimal("0.00")
            unit_price = base_price + extra
            QuotationLine.objects.create(
                quotation=quotation,
                product=t_line.product,
                variant=t_line.variant,
                quantity=t_line.quantity,
                unit_price=unit_price,
                tax_rate=Decimal("10.00"),  # Default standard tax
                amount=unit_price * t_line.quantity
            )

        QuotationService.recalculate_totals(quotation)
        return quotation

    @staticmethod
    def send_quotation(quotation):
        """Mark quotation as sent/active quotation."""
        if quotation.status == Quotation.Status.DRAFT:
            quotation.status = Quotation.Status.QUOTATION
            quotation.save(update_fields=["status"])
        return quotation

    @staticmethod
    def confirm_quotation(quotation):
        """Confirm quotation by customer/staff."""
        quotation.status = Quotation.Status.CONFIRMED
        quotation.save(update_fields=["status"])
        return quotation

    @staticmethod
    def convert_to_subscription(quotation):
        """
        Convert a confirmed quotation into an active or confirmed subscription.
        Copies all lines and links the records.
        """
        if hasattr(quotation, "subscription") and quotation.subscription:
            return quotation.subscription

        # Determine plan
        if quotation.template and quotation.template.plan:
            plan = quotation.template.plan
        else:
            plan = Plan.objects.filter(is_active=True).first()
            if not plan:
                raise ValueError("No active plan available to attach to the subscription.")

        subscription = Subscription.objects.create(
            customer=quotation.customer,
            plan=plan,
            quotation=quotation,
            start_date=quotation.issue_date or timezone.now().date(),
            expiry_date=quotation.expiry_date,
            payment_terms=quotation.payment_terms,
            status=Subscription.Status.CONFIRMED
        )

        for line in quotation.lines.all():
            SubscriptionLine.objects.create(
                subscription=subscription,
                product=line.product,
                variant=line.variant,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_rate=line.tax_rate,
                amount=line.amount
            )

        quotation.status = Quotation.Status.CONVERTED
        quotation.save(update_fields=["status"])
        return subscription
