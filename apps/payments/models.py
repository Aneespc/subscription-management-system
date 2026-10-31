from django.conf import settings
from django.db import models


class Payment(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = "CASH"
        BANK_TRANSFER = "BANK_TRANSFER"
        CARD = "CARD"
        UPI = "UPI"
        OTHER = "OTHER"

    payment_number = models.CharField(max_length=50, unique=True)
    invoice = models.ForeignKey("invoicing.Invoice", on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_date = models.DateTimeField()
    transaction_reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments_recorded"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["payment_date"]),
            models.Index(fields=["payment_method"]),
        ]

    def __str__(self):
        return self.payment_number