from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache_utils import bump_version

# Both the stub and the real Invoice labels are listed, so this keeps working after integration
WATCHED = {
    "payments.Payment", "payments.Invoice", "invoicing.Invoice",
    "subscriptions.Subscription", "accounts.CustomerProfile",
}


@receiver([post_save, post_delete], dispatch_uid="dashboard_cache_bump")
def refresh_dashboard_cache(sender, **kwargs):
    if sender._meta.label in WATCHED:
        # After commit, so a reader can't re-cache half-saved data
        transaction.on_commit(bump_version)