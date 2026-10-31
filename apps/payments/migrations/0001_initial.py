from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('invoicing', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payment_number', models.CharField(max_length=50, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('payment_method', models.CharField(choices=[('CASH', 'Cash'), ('BANK_TRANSFER', 'Bank Transfer'), ('CARD', 'Card'), ('UPI', 'Upi'), ('OTHER', 'Other')], max_length=20)),
                ('payment_date', models.DateTimeField()),
                ('transaction_reference', models.CharField(blank=True, max_length=100)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='invoicing.invoice')),
                ('recorded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payments_recorded', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [
                    models.Index(fields=['payment_date'], name='payments_pa_payment_22c7bc_idx'),
                    models.Index(fields=['payment_method'], name='payments_pa_payment_b669f1_idx'),
                ],
            },
        ),
    ]
