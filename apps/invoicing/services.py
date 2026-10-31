import io
import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.invoicing.models import Invoice, InvoiceLine, InvoiceTaxLine, Tax, quantize_currency
from apps.subscriptions.models import Subscription

logger = logging.getLogger(__name__)


class TaxService:
    @classmethod
    def resolve_tax(cls, tax_rate):
        """
        SubscriptionLine stores tax_rate (not a Tax FK).
        Resolve matching active Tax by rate where possible; otherwise returns None and generic label.
        """
        rate = Decimal(str(tax_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        matching_tax = Tax.objects.filter(is_active=True, rate=rate).first()
        tax_name = matching_tax.name if matching_tax else f"Tax ({rate}%)"
        return matching_tax, tax_name, rate

    @classmethod
    def calculate_line_tax(cls, taxable_amount, tax_rate):
        """Calculate tax on a specific taxable amount."""
        rate = Decimal(str(tax_rate))
        if rate <= Decimal("0.00") or taxable_amount <= Decimal("0.00"):
            return Decimal("0.00")
        tax_val = taxable_amount * (rate / Decimal("100.00"))
        return quantize_currency(tax_val)

    @classmethod
    def aggregate_tax_lines(cls, invoice, lines_data):
        """
        Given invoice and list of dicts/lines with 'taxable_amount', 'tax_rate', 'tax_name',
        group by (tax_name, tax_rate) and create InvoiceTaxLine instances.
        """
        grouped = defaultdict(lambda: {"taxable_amount": Decimal("0.00"), "tax_rate": Decimal("0.00")})

        for item in lines_data:
            tax_rate = Decimal(str(item["tax_rate"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            tax_name = item.get("tax_name") or f"Tax ({tax_rate}%)"
            if tax_rate > Decimal("0.00"):
                key = (tax_name, tax_rate)
                grouped[key]["taxable_amount"] += quantize_currency(item["taxable_amount"])
                grouped[key]["tax_rate"] = tax_rate

        tax_line_instances = []
        for (tax_name, tax_rate), data in grouped.items():
            taxable = quantize_currency(data["taxable_amount"])
            tax_amt = quantize_currency(taxable * (tax_rate / Decimal("100.00")))
            tax_line_instances.append(
                InvoiceTaxLine(
                    invoice=invoice,
                    tax_name=tax_name,
                    tax_rate=tax_rate,
                    taxable_amount=taxable,
                    tax_amount=tax_amt,
                )
            )

        return tax_line_instances


class InvoiceService:
    @classmethod
    def generate_for_subscription(cls, subscription, period_start, period_end):
        """
        Generates an invoice for a given subscription and billing period.
        Atomic and idempotent (get_or_create style, catching IntegrityError on unique constraint).
        Snapshots product, description, price, tax rate, and applies eligible discounts.
        """
        # Lazy import of DiscountService to avoid circular dependency
        from apps.discounts.services import DiscountService

        # 1. Quick idempotency check before doing heavy calculations
        existing_invoice = Invoice.objects.filter(
            subscription=subscription,
            billing_period_start=period_start,
            billing_period_end=period_end,
        ).first()
        if existing_invoice:
            logger.info(
                f"Invoice already exists for subscription {subscription.subscription_number} "
                f"({period_start} to {period_end}): {existing_invoice.invoice_number}"
            )
            return existing_invoice

        issue_date = timezone.now().date()
        payment_days = subscription.payment_terms if subscription.payment_terms is not None else 30
        due_date = issue_date + timedelta(days=payment_days)

        # Snapshot lines from subscription
        sub_lines = list(subscription.lines.select_related("product").all())
        raw_subtotal = Decimal("0.00")
        line_items_data = []

        for sub_line in sub_lines:
            qty = sub_line.quantity
            unit_price = quantize_currency(sub_line.unit_price)
            line_amount = quantize_currency(Decimal(qty) * unit_price)
            raw_subtotal += line_amount

            tax_obj, tax_name, tax_rate = TaxService.resolve_tax(sub_line.tax_rate)

            line_items_data.append({
                "sub_line": sub_line,
                "product": sub_line.product,
                "description": f"{sub_line.product.name}" + (f" - {sub_line.variant}" if sub_line.variant else ""),
                "quantity": qty,
                "unit_price": unit_price,
                "raw_amount": line_amount,
                "tax_obj": tax_obj,
                "tax_name": tax_name,
                "tax_rate": tax_rate,
                "discount_amount": Decimal("0.00"),
                "net_amount": line_amount,
            })

        raw_subtotal = quantize_currency(raw_subtotal)

        # 2. Evaluate eligible discounts
        eligible_discounts = DiscountService.get_eligible_discounts(
            subscription=subscription,
            lines=sub_lines,
            subtotal=raw_subtotal,
            on_date=issue_date,
        )

        selected_discount = None
        max_discount_amount = Decimal("0.00")

        # Pick the discount yielding the greatest savings
        for d in eligible_discounts:
            d_amt = DiscountService.calculate(d, lines=sub_lines, subtotal=raw_subtotal)
            if d_amt > max_discount_amount:
                max_discount_amount = d_amt
                selected_discount = d

        total_discount = quantize_currency(max_discount_amount)

        # Distribute discount across lines for accurate line amounts and line taxes
        if total_discount > Decimal("0.00") and raw_subtotal > Decimal("0.00"):
            remaining_disc = total_discount
            # If applies to specific products, distribute only to those
            if selected_discount and selected_discount.applies_to == selected_discount.AppliesTo.PRODUCTS:
                disc_prod_ids = set(selected_discount.products.values_list("id", flat=True))
                target_items = [item for item in line_items_data if item["product"].id in disc_prod_ids]
            else:
                target_items = line_items_data

            target_subtotal = sum(it["raw_amount"] for it in target_items)
            for idx, item in enumerate(target_items):
                if idx == len(target_items) - 1:
                    item_disc = min(remaining_disc, item["raw_amount"])
                else:
                    if target_subtotal > Decimal("0.00"):
                        item_disc = quantize_currency(total_discount * (item["raw_amount"] / target_subtotal))
                        item_disc = min(item_disc, remaining_disc, item["raw_amount"])
                    else:
                        item_disc = Decimal("0.00")
                item["discount_amount"] = item_disc
                item["net_amount"] = quantize_currency(item["raw_amount"] - item_disc)
                remaining_disc = quantize_currency(remaining_disc - item_disc)

        # 3. Calculate taxes on net taxable amounts
        taxable_lines_for_aggregation = [
            {
                "taxable_amount": item["net_amount"],
                "tax_rate": item["tax_rate"],
                "tax_name": item["tax_name"],
            }
            for item in line_items_data
        ]

        # 4. Create invoice atomically
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
                    tax_amount=Decimal("0.00"),  # calculated below
                    total_amount=Decimal("0.00"),  # calculated below
                    status=Invoice.Status.DRAFT,
                )
                invoice.save()

                # Generate and bulk create tax lines
                tax_lines = TaxService.aggregate_tax_lines(invoice, taxable_lines_for_aggregation)
                total_tax = sum((tl.tax_amount for tl in tax_lines), Decimal("0.00"))
                total_tax = quantize_currency(total_tax)

                if tax_lines:
                    InvoiceTaxLine.objects.bulk_create(tax_lines)

                # Update invoice tax and total
                invoice.tax_amount = total_tax
                final_total = max(Decimal("0.00"), raw_subtotal - total_discount + total_tax)
                invoice.total_amount = quantize_currency(final_total)
                invoice.save(update_fields=["tax_amount", "total_amount"])

                # Create InvoiceLine snapshot rows
                invoice_line_objs = [
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
                    for item in line_items_data
                ]
                InvoiceLine.objects.bulk_create(invoice_line_objs)

                # 5. Apply discount usage concurrency-safely
                if selected_discount and total_discount > Decimal("0.00"):
                    DiscountService.apply(selected_discount, invoice, total_discount)

                logger.info(
                    f"Generated invoice {invoice.invoice_number} for subscription {subscription.subscription_number}. "
                    f"Subtotal: ${invoice.subtotal}, Discount: ${invoice.discount_amount}, "
                    f"Tax: ${invoice.tax_amount}, Total: ${invoice.total_amount}"
                )
                return invoice

        except IntegrityError:
            # Handles race condition where concurrent worker created the exact same invoice
            logger.warning(
                f"Concurrent invoice creation detected for subscription {subscription.subscription_number} "
                f"({period_start} to {period_end}). Fetching existing record."
            )
            return Invoice.objects.get(
                subscription=subscription,
                billing_period_start=period_start,
                billing_period_end=period_end,
            )

    @classmethod
    def generate_due_invoices(cls, run_date=None):
        """
        Selects subscriptions with status ACTIVE and next_billing_date <= run_date.
        Processes in batches, advances next_billing_date by plan billing_interval
        (DAILY, WEEKLY, MONTHLY, YEARLY) with correct month-end handling via dateutil.relativedelta.
        One subscription failure does not stop the batch.
        Returns a summary dict.
        """
        if run_date is None:
            run_date = timezone.now().date()

        # Query active subscriptions due for billing
        due_subscriptions = (
            Subscription.objects.filter(
                status=Subscription.Status.ACTIVE,
                next_billing_date__lte=run_date,
            )
            .select_related("customer", "customer__user", "plan")
            .prefetch_related("lines", "lines__product")
            .order_by("id")
        )

        created_invoices = []
        failed_subscriptions = []
        skipped_count = 0

        for sub in due_subscriptions.iterator(chunk_size=100):
            # Skip if status changed or if expired
            if sub.status != Subscription.Status.ACTIVE:
                skipped_count += 1
                continue

            period_start = sub.next_billing_date
            if not period_start:
                skipped_count += 1
                continue

            # Calculate period_end and next billing date according to plan interval
            plan = sub.plan
            interval_count = max(1, plan.billing_interval_count or 1)
            interval_type = plan.billing_interval

            if interval_type == plan.BillingInterval.DAILY:
                delta = relativedelta(days=interval_count)
            elif interval_type == plan.BillingInterval.WEEKLY:
                delta = relativedelta(weeks=interval_count)
            elif interval_type == plan.BillingInterval.YEARLY:
                delta = relativedelta(years=interval_count)
            else:  # MONTHLY (default)
                delta = relativedelta(months=interval_count)

            next_billing = period_start + delta
            period_end = next_billing - timedelta(days=1)

            # Check if subscription has expired
            if sub.expiry_date and period_start > sub.expiry_date:
                sub.status = Subscription.Status.EXPIRED
                sub.save(update_fields=["status"])
                skipped_count += 1
                continue

            try:
                invoice = cls.generate_for_subscription(sub, period_start, period_end)
                created_invoices.append(invoice)

                # Advance next_billing_date
                sub.next_billing_date = next_billing
                if sub.expiry_date and next_billing > sub.expiry_date:
                    sub.status = Subscription.Status.EXPIRED
                sub.save(update_fields=["next_billing_date", "status"])

            except Exception as exc:
                logger.exception(
                    f"Error generating invoice for subscription {sub.subscription_number}: {exc}"
                )
                failed_subscriptions.append({
                    "subscription_id": sub.id,
                    "subscription_number": sub.subscription_number,
                    "error": str(exc),
                })

        return {
            "run_date": run_date,
            "created": len(created_invoices),
            "skipped": skipped_count,
            "failed": len(failed_subscriptions),
            "invoices": created_invoices,
            "errors": failed_subscriptions,
        }

    @classmethod
    def confirm(cls, invoice):
        """
        Transitions an invoice from DRAFT to CONFIRMED.
        """
        if invoice.status != Invoice.Status.DRAFT:
            raise ValidationError(
                f"Cannot confirm invoice in '{invoice.status}' status. Only DRAFT invoices can be confirmed."
            )
        invoice.status = Invoice.Status.CONFIRMED
        invoice.save(update_fields=["status", "updated_at"])
        logger.info(f"Invoice {invoice.invoice_number} transitioned to CONFIRMED.")
        return invoice

    @classmethod
    def cancel(cls, invoice):
        """
        Transitions an invoice from DRAFT or CONFIRMED to CANCELLED.
        Paid invoices cannot be cancelled.
        """
        if invoice.status == Invoice.Status.PAID:
            raise ValidationError("Paid invoices cannot be cancelled or edited.")
        if invoice.status == Invoice.Status.CANCELLED:
            return invoice

        invoice.status = Invoice.Status.CANCELLED
        invoice.save(update_fields=["status", "updated_at"])
        logger.info(f"Invoice {invoice.invoice_number} transitioned to CANCELLED.")
        return invoice

    @classmethod
    def mark_paid(cls, invoice, payment=None):
        """
        Public method exposed for Member 4's payments app to call.
        Transitions an invoice to PAID.
        Paid invoices cannot be edited or cancelled.
        """
        if invoice.status == Invoice.Status.CANCELLED:
            raise ValidationError("Cancelled invoices cannot be marked as paid.")
        if invoice.status == Invoice.Status.PAID:
            return invoice

        invoice.status = Invoice.Status.PAID
        invoice.save(update_fields=["status", "updated_at"])
        logger.info(
            f"Invoice {invoice.invoice_number} marked as PAID" +
            (f" via payment {payment.id}" if payment else ".")
        )
        return invoice

    @classmethod
    def render_pdf(cls, invoice):
        """
        Renders print-ready PDF bytes for the invoice using xhtml2pdf.
        """
        from xhtml2pdf import pisa

        context = {
            "invoice": invoice,
            "customer": invoice.customer,
            "lines": invoice.lines.select_related("product", "tax").all(),
            "tax_lines": invoice.tax_lines.all(),
            "discount_usages": invoice.discount_usages.select_related("discount").all(),
            "now": timezone.now(),
        }
        html_content = render_to_string("invoicing/invoice_pdf.html", context)

        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer)
        if pisa_status.err:
            logger.error(f"xhtml2pdf error creating PDF for invoice {invoice.invoice_number}: {pisa_status.err}")
            raise RuntimeError(f"Failed to render PDF: error code {pisa_status.err}")

        return pdf_buffer.getvalue()

    @classmethod
    def send(cls, invoice, recipient_email=None):
        """
        Sends invoice notification email with PDF attached using Django's email backend.
        """
        if recipient_email is None:
            recipient_email = (
                invoice.customer.billing_email or
                invoice.customer.user.email
            )

        if not recipient_email:
            raise ValidationError(
                f"No billing email address found for customer {invoice.customer}."
            )

        pdf_bytes = cls.render_pdf(invoice)

        subject = f"Invoice {invoice.invoice_number} from Brightloop Software"
        body = (
            f"Dear {invoice.customer},\n\n"
            f"Please find attached your invoice {invoice.invoice_number} for the period "
            f"{invoice.billing_period_start} to {invoice.billing_period_end}.\n\n"
            f"Amount Due: ${invoice.total_amount}\n"
            f"Due Date: {invoice.due_date}\n"
            f"Status: {invoice.get_status_display()}\n\n"
            f"Thank you for choosing Brightloop Software!\n"
        )

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "billing@brightloopsoftware.com")
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[recipient_email],
        )
        email.attach(
            filename=f"{invoice.invoice_number}.pdf",
            content=pdf_bytes,
            mimetype="application/pdf",
        )
        email.send()
        logger.info(f"Sent invoice {invoice.invoice_number} to {recipient_email}.")
        return True

