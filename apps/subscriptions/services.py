from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from .models import Subscription, SubscriptionLine


class SubscriptionService:
    def activate(self, subscription):
        """
        Activate subscription.
        Validates minimum quantity against plan requirements.
        Sets next billing date according to plan interval.
        """
        # Validate minimum quantity
        if not subscription.meets_minimum_quantity:
            raise ValueError(
                f"Cannot activate: Total quantity ({subscription.total_quantity}) "
                f"is less than plan minimum quantity ({subscription.plan.minimum_quantity})."
            )

        subscription.status = Subscription.Status.ACTIVE
        if not subscription.next_billing_date:
            subscription.next_billing_date = subscription.calculate_next_billing_date(subscription.start_date)

        subscription.save(update_fields=["status", "next_billing_date"])
        return subscription

    def pause(self, subscription):
        """
        Pause an active subscription.
        Enforces plan.allow_pause policy.
        """
        if not subscription.plan.allow_pause:
            raise ValueError(f"Plan '{subscription.plan.name}' does not allow pausing.")

        if subscription.status != Subscription.Status.ACTIVE:
            raise ValueError(f"Only ACTIVE subscriptions can be paused. Current: {subscription.get_status_display()}")

        subscription.status = Subscription.Status.PAUSED
        subscription.save(update_fields=["status"])
        return subscription

    def resume(self, subscription):
        """Resume a paused subscription."""
        if subscription.status != Subscription.Status.PAUSED:
            raise ValueError("Only PAUSED subscriptions can be resumed.")

        subscription.status = Subscription.Status.ACTIVE
        subscription.save(update_fields=["status"])
        return subscription

    def renew(self, subscription, additional_days=None):
        """
        Renew a subscription.
        Enforces plan.allow_renewal policy.
        Extends expiry date and restores active status.
        """
        if not subscription.plan.allow_renewal:
            raise ValueError(f"Plan '{subscription.plan.name}' does not allow renewals.")

        today = timezone.now().date()
        base_date = subscription.expiry_date if (subscription.expiry_date and subscription.expiry_date > today) else today

        if additional_days is None:
            interval = subscription.plan.billing_interval
            if interval == "DAILY":
                additional_days = 1
            elif interval == "WEEKLY":
                additional_days = 7
            elif interval == "MONTHLY":
                additional_days = 30
            elif interval == "YEARLY":
                additional_days = 365
            else:
                additional_days = 30

        subscription.expiry_date = base_date + timedelta(days=additional_days)
        subscription.status = Subscription.Status.ACTIVE
        subscription.next_billing_date = subscription.calculate_next_billing_date(today)
        subscription.save(update_fields=["expiry_date", "status", "next_billing_date"])
        return subscription

    def close(self, subscription, force=False):
        """
        Close a subscription.
        Enforces plan.allow_early_close policy unless forced or past expiry.
        """
        today = timezone.now().date()
        is_early = subscription.expiry_date and subscription.expiry_date > today

        if is_early and not force and not subscription.plan.allow_early_close:
            raise ValueError(f"Plan '{subscription.plan.name}' does not permit early closure.")

        subscription.status = Subscription.Status.CLOSED
        subscription.save(update_fields=["status"])
        return subscription

    def check_and_auto_close_expired(self, current_date=None):
        """
        Auto-close subscriptions that have reached expiry where plan.auto_close is True.
        """
        if not current_date:
            current_date = timezone.now().date()

        expired_subs = Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
            plan__auto_close=True,
            expiry_date__lte=current_date
        )
        count = 0
        for sub in expired_subs:
            sub.status = Subscription.Status.CLOSED
            sub.save(update_fields=["status"])
            count += 1
        return count
