import io
import logging
from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import models
from django.template.loader import render_to_string
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.invoicing.models import Invoice, InvoiceLine, InvoiceTaxLine, quantize_currency
from apps.products.models import Tax
from apps.payments.services import calculate_outstanding
from apps.subscriptions.models import Subscription

logger = logging.getLogger(__name__)


class TaxService:
    @classmethod
    def resolve_tax(cls, tax_rate):
        rate = Decimal(str(tax_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        matching_tax = Tax.objects.filter(is_active=True, rate=rate).first()
        tax_name = matching_tax.name if matching_tax else f"Tax ({rate}%)"
        return matching_tax, tax_name, rate

    @classmethod
    def calculate_line_tax(cls, taxable_amount, tax_rate):
        rate = Decimal(str(tax_rate))
        if rate <= Decimal("0.00") or taxable_amount <= Decimal("0.00"):
            return Decimal("0.00")
        return quantize_currency(taxable_amount * (rate / Decimal("100.00")))

    @classmethod
    def aggregate_tax_lines(cls, invoice, lines_data):
        grouped = defaultdict(lambda: Decimal("0.00"))
        for item in lines_data:
            tax_rate = Decimal(str(item["tax_rate"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if tax_rate <= Decimal("0.00"):
                continue
            tax_name = item.get("tax_name") or f"Tax ({tax_rate}%)"
            grouped[(tax_name, tax_rate)] += quantize_currency(item["taxable_amount"])
        return [
            InvoiceTaxLine(
                invoice=invoice,
                tax_name=tax_name,
                tax_rate=tax_rate,
                taxable_amount=taxable,
                tax_amount=quantize_currency(taxable * (tax_rate / Decimal("100.00"))),
            )
            for (tax_name, tax_rate), taxable in grouped.items()
        ]


class InvoiceService:
    MAX_CATCH_UP_PERIODS = 36

    @classmethod
    def generate_for_subscription(cls, subscription, period_start, period_end):
        from apps.discounts.services import DiscountService

        existing = Invoice.objects.filter(
            subscription=subscription,
            billing_period_start=period_start,
            billing_period_end=period_end,
        ).first()
        if existing:
            return existing

        issue_date = timezone.localdate()
        due_date = issue_date + timedelta(days=subscription.payment_terms_days)

        sub_lines = list(subscription.lines.select_related("product", "variant"))
        raw_subtotal = Decimal("0.00")
        line_items = []
        for sub_line in sub_lines:
            unit_price = quantize_currency(sub_line.unit_price)
            line_amount = quantize_currency(Decimal(sub_line.quantity) * unit_price)
            raw_subtotal += line_amount
            tax_obj, tax_name, tax_rate = TaxService.resolve_tax(sub_line.tax_rate)
            description = sub_line.product.name
            if sub_line.variant:
                description += f" ({sub_line.variant.attribute_name}: {sub_line.variant.attribute_value})"
            line_items.append(
                {
                    "product": sub_line.product,
                    "description": description,
                    "quantity": sub_line.quantity,
                    "unit_price": unit_price,
                    "raw_amount": line_amount,
                    "tax_obj": tax_obj,
                    "tax_name": tax_name,
                    "tax_rate": tax_rate,
                    "discount_amount": Decimal("0.00"),
                    "net_amount": line_amount,
                }
            )
        raw_subtotal = quantize_currency(raw_subtotal)

        eligible = DiscountService.get_eligible_discounts(
            subscription=subscription, lines=sub_lines, subtotal=raw_subtotal, on_date=issue_date
        )
        selected_discount, max_amount = None, Decimal("0.00")
        for discount in eligible:
            amount = DiscountService.calculate(discount, lines=sub_lines, subtotal=raw_subtotal)
            if amount > max_amount:
                selected_discount, max_amount = discount, amount
        total_discount = quantize_currency(max_amount)

        if total_discount > Decimal("0.00") and raw_subtotal > Decimal("0.00"):
            if selected_discount.applies_to == selected_discount.AppliesTo.PRODUCTS:
                product_ids = set(selected_discount.products.values_list("id", flat=True))
                targets = [item for item in line_items if item["product"].id in product_ids]
            else:
                targets = line_items
            target_subtotal = sum((item["raw_amount"] for item in targets), Decimal("0.00"))
            remaining = total_discount
            for idx, item in enumerate(targets):
                if idx == len(targets) - 1:
                    item_disc = min(remaining, item["raw_amount"])
                elif target_subtotal > Decimal("0.00"):
                    item_disc = quantize_currency(total_discount * (item["raw_amount"] / target_subtotal))
                    item_disc = min(item_disc, remaining, item["raw_amount"])
                else:
                    item_disc = Decimal("0.00")
                item["discount_amount"] = item_disc
                item["net_amount"] = quantize_currency(item["raw_amount"] - item_disc)
                remaining = quantize_currency(remaining - item_disc)

        tax_inputs = [
            {"taxable_amount": item["net_amount"], "tax_rate": item["tax_rate"], "tax_name": item["tax_name"]}
            for item in line_items
        ]

        try:
            with transaction.atomic():
                invoice = Invoice(
                    customer=subscription.customer,
                    subscription=subscription,
                    issue_date=issue_date,
                    due_date=due_date,
                    billing_period_start=period_start,
                    billing_period_end=period_end,
                    subtotal=raw_subtotal,
                    discount_amount=total_discount,
                    status=Invoice.Status.DRAFT,
                )
                invoice.save()
                tax_lines = TaxService.aggregate_tax_lines(invoice, tax_inputs)
                total_tax = quantize_currency(sum((tl.tax_amount for tl in tax_lines), Decimal("0.00")))
                if tax_lines:
                    InvoiceTaxLine.objects.bulk_create(tax_lines)
                invoice.tax_amount = total_tax
                invoice.total_amount = quantize_currency(max(Decimal("0.00"), raw_subtotal - total_discount + total_tax))
                invoice.save(update_fields=["tax_amount", "total_amount", "updated_at"])
                InvoiceLine.objects.bulk_create(
                    [
                        InvoiceLine(
                            invoice=invoice,
                            product=item["product"],
                            description=item["description"],
                            quantity=item["quantity"],
                            unit_price=item["unit_price"],
                            tax=item["tax_obj"],
                            tax_rate=item["tax_rate"],
                            discount_amount=item["discount_amount"],
                            amount=item["net_amount"],
                        )
                        for item in line_items
                    ]
                )
                if selected_discount and total_discount > Decimal("0.00"):
                    DiscountService.apply(selected_discount, invoice, total_discount)
                return invoice
        except IntegrityError:
            return Invoice.objects.get(
                subscription=subscription,
                billing_period_start=period_start,
                billing_period_end=period_end,
            )

    @classmethod
    def generate_due_invoices(cls, run_date=None):
        from apps.subscriptions.services import SubscriptionService

        run_date = run_date or timezone.localdate()
        auto_closed = SubscriptionService().check_and_auto_close_expired(run_date)

        due_subscriptions = (
            Subscription.objects.filter(status=Subscription.Status.ACTIVE, next_billing_date__lte=run_date)
            .select_related("customer", "customer__user", "plan")
            .order_by("id")
        )

        created, errors, skipped = [], [], 0
        for sub in due_subscriptions.iterator(chunk_size=100):
            if not sub.next_billing_date:
                skipped += 1
                continue
            periods_billed = 0
            try:
                while sub.next_billing_date and sub.next_billing_date <= run_date and periods_billed < cls.MAX_CATCH_UP_PERIODS:
                    period_start = sub.next_billing_date
                    if sub.expiry_date and period_start > sub.expiry_date:
                        if sub.plan.auto_close:
                            sub.status = Subscription.Status.CLOSED
                            sub.save(update_fields=["status", "updated_at"])
                        break
                    next_billing = period_start + sub.plan.interval_delta()
                    period_end = next_billing - timedelta(days=1)
                    with transaction.atomic():
                        invoice = cls.generate_for_subscription(sub, period_start, period_end)
                        sub.next_billing_date = next_billing
                        if sub.expiry_date and next_billing > sub.expiry_date and sub.plan.auto_close:
                            sub.status = Subscription.Status.CLOSED
                        sub.save(update_fields=["next_billing_date", "status", "updated_at"])
                    created.append(invoice)
                    periods_billed += 1
                    if sub.status != Subscription.Status.ACTIVE:
                        break
                if not periods_billed:
                    skipped += 1
            except Exception as exc:
                logger.exception("Invoice generation failed for %s", sub.subscription_number)
                errors.append(
                    {"subscription_id": sub.id, "subscription_number": sub.subscription_number, "error": str(exc)}
                )

        return {
            "run_date": run_date,
            "created": len(created),
            "skipped": skipped,
            "failed": len(errors),
            "auto_closed": auto_closed,
            "invoices": created,
            "errors": errors,
        }

    @classmethod
    def confirm(cls, invoice):
        if invoice.status != Invoice.Status.DRAFT:
            raise ValidationError("Only draft invoices can be confirmed.")
        invoice.status = Invoice.Status.CONFIRMED
        invoice.save(update_fields=["status", "updated_at"])
        return invoice

    @classmethod
    def cancel(cls, invoice):
        if invoice.status == Invoice.Status.PAID:
            raise ValidationError("Paid invoices cannot be cancelled.")
        if invoice.payments.exists():
            raise ValidationError("Invoices with recorded payments cannot be cancelled.")
        if invoice.status == Invoice.Status.CANCELLED:
            return invoice
        invoice.status = Invoice.Status.CANCELLED
        invoice.save(update_fields=["status", "updated_at"])
        return invoice

    @classmethod
    def mark_paid(cls, invoice, payment=None):
        if invoice.status == Invoice.Status.CANCELLED:
            raise ValidationError("Cancelled invoices cannot be marked as paid.")
        if invoice.status == Invoice.Status.PAID:
            return invoice
        invoice.status = Invoice.Status.PAID
        invoice.save(update_fields=["status", "updated_at"])
        return invoice

    @classmethod
    def render_pdf(cls, invoice):
        from xhtml2pdf import pisa

        html = render_to_string(
            "invoicing/invoice_pdf.html",
            {
                "invoice": invoice,
                "customer": invoice.customer,
                "lines": invoice.lines.select_related("product"),
                "tax_lines": invoice.tax_lines.all(),
                "discount_usages": invoice.discount_usages.select_related("discount"),
                "paid": invoice.total_amount - calculate_outstanding(invoice),
                "outstanding": calculate_outstanding(invoice),
                "now": timezone.now(),
            },
        )
        buffer = io.BytesIO()
        status = pisa.CreatePDF(html, dest=buffer, encoding="utf-8")
        if status.err:
            raise RuntimeError(f"Failed to render PDF (error code {status.err}).")
        return buffer.getvalue()

    EMAIL_KINDS = {
        "invoice": ("Invoice {number} from Brightloop Software", "Please find attached invoice {number} for the period {start} to {end}."),
        "due": ("Reminder: invoice {number} is due on {due}", "This is a friendly reminder that invoice {number} is due on {due}. The invoice is attached for your records."),
        "overdue": ("Overdue: invoice {number} was due on {due}", "Invoice {number} was due on {due} and is still outstanding. Please arrange payment at your earliest convenience. The invoice is attached."),
    }

    @classmethod
    def send(cls, invoice, recipient_email=None, kind="invoice"):
        recipient_email = recipient_email or invoice.customer.contact_email
        if not recipient_email:
            raise ValidationError(f"No email address on file for {invoice.customer}.")
        subject, intro = cls.EMAIL_KINDS[kind]
        fmt = {
            "number": invoice.invoice_number,
            "start": invoice.billing_period_start,
            "end": invoice.billing_period_end,
            "due": invoice.due_date.strftime("%d %b %Y"),
        }
        outstanding = calculate_outstanding(invoice)
        lines = "\n".join(
            f"  - {line.description} x {line.quantity} @ ₹{line.unit_price} = ₹{line.amount}" for line in invoice.lines.all()
        )
        body = (
            f"Dear {invoice.customer},\n\n{intro.format(**fmt)}\n\n{lines}\n\n"
            f"Subtotal: ₹{invoice.subtotal}\nDiscount: ₹{invoice.discount_amount}\nTax: ₹{invoice.tax_amount}\n"
            f"Total: ₹{invoice.total_amount}\nAmount outstanding: ₹{outstanding}\nDue date: {fmt['due']}\n\n"
            "Thank you for choosing Brightloop Software.\n"
        )
        email = EmailMessage(
            subject=subject.format(**fmt),
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[recipient_email],
        )
        email.attach(f"{invoice.invoice_number}.pdf", cls.render_pdf(invoice), "application/pdf")
        email.send()
        now = timezone.now()
        if kind == "invoice":
            invoice.sent_at = now
            invoice.save(update_fields=["sent_at", "updated_at"])
        else:
            invoice.reminder_sent_at = now
            invoice.reminder_count += 1
            invoice.save(update_fields=["reminder_sent_at", "reminder_count", "updated_at"])
        return True

    @classmethod
    def send_due_notifications(cls, today=None, days_before=None, repeat_days=None):
        from datetime import timedelta as _td

        today = today or timezone.localdate()
        days_before = settings.INVOICE_REMINDER_DAYS_BEFORE if days_before is None else days_before
        repeat_days = settings.INVOICE_REMINDER_REPEAT_DAYS if repeat_days is None else repeat_days
        confirmed = Invoice.objects.filter(status=Invoice.Status.CONFIRMED).select_related("customer", "customer__user")
        result = {"invoice": 0, "due": 0, "overdue": 0, "failed": []}

        def deliver(invoice, kind):
            try:
                cls.send(invoice, kind=kind)
                result[kind] += 1
            except Exception as exc:
                logger.exception("Failed to email %s for %s", kind, invoice.invoice_number)
                result["failed"].append({"invoice": invoice.invoice_number, "kind": kind, "error": str(exc)})

        for invoice in confirmed.filter(sent_at__isnull=True).order_by("id"):
            deliver(invoice, "invoice")

        due_window_end = today + _td(days=days_before)
        for invoice in confirmed.filter(
            due_date__gte=today, due_date__lte=due_window_end, reminder_sent_at__isnull=True
        ).order_by("due_date"):
            deliver(invoice, "due")

        repeat_cutoff = today - _td(days=repeat_days)
        overdue = confirmed.filter(due_date__lt=today).filter(
            models.Q(reminder_sent_at__isnull=True) | models.Q(reminder_sent_at__date__lte=repeat_cutoff)
        )
        for invoice in overdue.order_by("due_date"):
            deliver(invoice, "overdue")
        return result
