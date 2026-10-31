from rest_framework import serializers

from apps.invoicing.models import Invoice
from .models import Payment
from .services import PaymentError, record_payment


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "payment_number", "invoice", "invoice_number", "amount",
            "payment_method", "payment_date", "transaction_reference",
            "notes", "recorded_by", "created_at",
        ]
        read_only_fields = fields


class PaymentCreateSerializer(serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all())
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_method = serializers.ChoiceField(choices=Payment.PaymentMethod.choices)
    payment_date = serializers.DateTimeField(required=False)
    transaction_reference = serializers.CharField(required=False, allow_blank=True, max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        invoice = validated_data.pop("invoice")
        amount = validated_data.pop("amount")
        method = validated_data.pop("payment_method")
        try:
            return record_payment(
                invoice=invoice, amount=amount, method=method,
                recorded_by=self.context["request"].user, **validated_data,
            )
        except PaymentError as exc:
            raise serializers.ValidationError({"detail": str(exc)})


class OverdueInvoiceSerializer(serializers.ModelSerializer):
    paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Invoice
        fields = ["id", "invoice_number", "due_date", "total_amount", "paid", "outstanding", "status"]