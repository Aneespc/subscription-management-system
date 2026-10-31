from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Subscription


class SubscriptionService:
    def activate(self, subscription):
        if subscription.status == Subscription.Status.ACTIVE:
            return subscription
        if subscription.status not in (
            Subscription.Status.DRAFT,
            Subscription.Status.QUOTATION,
            Subscription.Status.CONFIRMED,
        ):
            raise ValueError(f"A {subscription.get_status_display().lower()} subscription cannot be activated.")
        if not subscription.meets_minimum_quantity:
            raise ValueError(
                f"Cannot activate: total quantity ({subscription.total_quantity}) is below the plan minimum "
                f"({subscription.plan.minimum_quantity})."
            )
        subscription.status = Subscription.Status.ACTIVE
        if not subscription.next_billing_date:
            subscription.next_billing_date = subscription.calculate_next_billing_date(subscription.start_date)
        subscription.save(update_fields=["status", "next_billing_date", "updated_at"])
        return subscription

    def confirm(self, subscription):
        if subscription.status not in (Subscription.Status.DRAFT, Subscription.Status.QUOTATION):
            raise ValueError("Only draft or quotation subscriptions can be confirmed.")
        subscription.status = Subscription.Status.CONFIRMED
        subscription.save(update_fields=["status", "updated_at"])
        return subscription

    def pause(self, subscription):
        if not subscription.plan.allow_pause:
            raise ValueError(f"Plan '{subscription.plan.name}' does not allow pausing.")
        if subscription.status != Subscription.Status.ACTIVE:
            raise ValueError("Only active subscriptions can be paused.")
        subscription.status = Subscription.Status.PAUSED
        subscription.save(update_fields=["status", "updated_at"])
        return subscription

    def resume(self, subscription):
        if subscription.status != Subscription.Status.PAUSED:
            raise ValueError("Only paused subscriptions can be resumed.")
        today = timezone.localdate()
        subscription.status = Subscription.Status.ACTIVE
        if not subscription.next_billing_date or subscription.next_billing_date < today:
            subscription.next_billing_date = subscription.calculate_next_billing_date(today)
        subscription.save(update_fields=["status", "next_billing_date", "updated_at"])
        return subscription

    def renew(self, subscription, additional_days=None):
        if not subscription.plan.allow_renewal:
            raise ValueError(f"Plan '{subscription.plan.name}' does not allow renewals.")
        if subscription.status not in (Subscription.Status.ACTIVE, Subscription.Status.CLOSED):
            raise ValueError("Only active or closed subscriptions can be renewed.")
        today = timezone.localdate()
        base = subscription.expiry_date if subscription.expiry_date and subscription.expiry_date > today else today
        if additional_days:
            subscription.expiry_date = base + timedelta(days=additional_days)
        else:
            subscription.expiry_date = base + subscription.plan.interval_delta()
        was_closed = subscription.status == Subscription.Status.CLOSED
        subscription.status = Subscription.Status.ACTIVE
        if was_closed or not subscription.next_billing_date or subscription.next_billing_date < today:
            subscription.next_billing_date = subscription.calculate_next_billing_date(today)
        subscription.save(update_fields=["expiry_date", "status", "next_billing_date", "updated_at"])
        return subscription

    def close(self, subscription, force=False):
        if subscription.status == Subscription.Status.CLOSED:
            return subscription
        today = timezone.localdate()
        is_early = subscription.expiry_date and subscription.expiry_date > today
        if is_early and not force and not subscription.plan.allow_early_close:
            raise ValueError(f"Plan '{subscription.plan.name}' does not permit early closure.")
        subscription.status = Subscription.Status.CLOSED
        subscription.save(update_fields=["status", "updated_at"])
        return subscription

    def subscribe(self, customer, plan, formset, payment_terms=Subscription.PaymentTerms.NET_30):
        from apps.invoicing.services import InvoiceService

        today = timezone.localdate()
        with transaction.atomic():
            subscription = Subscription.objects.create(
                customer=customer, plan=plan, start_date=today, payment_terms=payment_terms,
                status=Subscription.Status.CONFIRMED,
            )
            formset.instance = subscription
            formset.save()
            subscription.next_billing_date = today
            self.activate(subscription)
            period_end = today + plan.interval_delta() - timedelta(days=1)
            invoice = InvoiceService.generate_for_subscription(subscription, today, period_end)
            InvoiceService.confirm(invoice)
            subscription.next_billing_date = period_end + timedelta(days=1)
            subscription.save(update_fields=["next_billing_date", "updated_at"])
        return subscription, invoice

    def check_and_auto_close_expired(self, current_date=None):
        current_date = current_date or timezone.localdate()
        with transaction.atomic():
            return Subscription.objects.filter(
                status__in=[Subscription.Status.ACTIVE, Subscription.Status.PAUSED],
                plan__auto_close=True,
                expiry_date__lt=current_date,
            ).update(status=Subscription.Status.CLOSED, updated_at=timezone.now())
