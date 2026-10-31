from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.subscriptions.models import Subscription, SubscriptionLine

from .models import Quotation, QuotationLine


class QuotationService:
    @staticmethod
    def recalculate_totals(quotation):
        subtotal = Decimal("0.00")
        tax_amount = Decimal("0.00")
        for line in quotation.lines.all():
            line_amount = line.unit_price * line.quantity
            if line.amount != line_amount:
                line.amount = line_amount
                line.save(update_fields=["amount"])
            subtotal += line_amount
            tax_amount += line_amount * line.tax_rate / Decimal("100")
        quotation.subtotal = subtotal.quantize(Decimal("0.01"))
        quotation.tax_amount = tax_amount.quantize(Decimal("0.01"))
        quotation.total_amount = (subtotal + tax_amount).quantize(Decimal("0.01"))
        quotation.save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])
        return quotation

    @staticmethod
    def create_from_template(template, customer, created_by=None, payment_terms=Quotation.PaymentTerms.NET_30):
        today = timezone.localdate()
        with transaction.atomic():
            quotation = Quotation.objects.create(
                customer=customer,
                template=template,
                plan=template.plan,
                created_by=created_by,
                issue_date=today,
                expiry_date=today + timedelta(days=template.validity_days),
                payment_terms=payment_terms,
                status=Quotation.Status.DRAFT,
            )
            for t_line in template.template_lines.select_related("product", "product__tax", "variant"):
                QuotationLine.objects.create(
                    quotation=quotation,
                    product=t_line.product,
                    variant=t_line.variant,
                    quantity=t_line.quantity,
                    unit_price=t_line.unit_price,
                    tax_rate=t_line.product.tax_rate,
                )
            QuotationService.recalculate_totals(quotation)
        return quotation

    @staticmethod
    def send_quotation(quotation):
        if not quotation.can_send():
            raise ValueError("Only draft quotations can be sent.")
        quotation.status = Quotation.Status.QUOTATION
        quotation.save(update_fields=["status", "updated_at"])
        return quotation

    @staticmethod
    def confirm_quotation(quotation):
        if quotation.is_expired:
            raise ValueError("This quotation has expired and can no longer be confirmed.")
        if quotation.status not in (Quotation.Status.DRAFT, Quotation.Status.QUOTATION):
            raise ValueError("Only sent quotations can be confirmed.")
        quotation.status = Quotation.Status.CONFIRMED
        quotation.save(update_fields=["status", "updated_at"])
        return quotation

    @staticmethod
    def convert_to_subscription(quotation):
        existing = getattr(quotation, "subscription", None)
        if existing:
            return existing
        if quotation.status != Quotation.Status.CONFIRMED:
            raise ValueError("Only confirmed quotations can be converted into subscriptions.")
        plan = quotation.plan or (quotation.template.plan if quotation.template else None)
        if plan is None:
            raise ValueError("Assign a plan to this quotation before converting it.")
        today = timezone.localdate()
        with transaction.atomic():
            subscription = Subscription.objects.create(
                customer=quotation.customer,
                plan=plan,
                quotation=quotation,
                start_date=today,
                expiry_date=today + plan.interval_delta(),
                payment_terms=quotation.payment_terms,
                status=Subscription.Status.CONFIRMED,
            )
            for line in quotation.lines.all():
                SubscriptionLine.objects.create(
                    subscription=subscription,
                    product=line.product,
                    variant=line.variant,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    tax_rate=line.tax_rate,
                )
            quotation.status = Quotation.Status.CONVERTED
            quotation.save(update_fields=["status", "updated_at"])
        return subscription
