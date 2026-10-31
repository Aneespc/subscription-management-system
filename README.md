# Subscription Management System — Member 3 (`discounts` & `invoicing`)

This repository branch contains the complete implementation of the **`discounts`** and **`invoicing`** applications for Brightloop Software's Subscription Management System.

---

## 1. Public Service APIs for Other Team Members

### Member 4 (`payments` app)
When a customer payment succeeds or fails, call our public service methods:

#### `InvoiceService.mark_paid(invoice, payment=None)`
- **Module:** `apps.invoicing.services.InvoiceService`
- **Arguments:**
  - `invoice`: `invoicing.Invoice` instance.
  - `payment`: Optional `payments.Payment` instance.
- **Behavior:**
  - Atomically transitions invoice from `CONFIRMED` (or `DRAFT`) to `PAID`.
  - Once marked `PAID`, the invoice becomes immutable and cannot be cancelled or altered.
  - Idempotent: Calling `mark_paid` on an already paid invoice is safe and returns the invoice.
  - If the invoice was previously `CANCELLED`, raises `django.core.exceptions.ValidationError`.

```python
from apps.invoicing.services import InvoiceService

# Mark invoice paid upon successful payment:
InvoiceService.mark_paid(invoice=payment.invoice, payment=payment)
```

---

### Member 2 (`subscriptions` app) / Automated Cron Jobs

#### `InvoiceService.generate_for_subscription(subscription, period_start, period_end)`
- **Module:** `apps.invoicing.services.InvoiceService`
- **Behavior:**
  - **Idempotent:** Guarantees no duplicate billing for the same subscription and period. If called repeatedly or concurrently, returns the existing invoice safely.
  - Snapshots product descriptions, unit prices, tax rates, and applied discounts at creation time.
  - Evaluates active discounts via `DiscountService` and applies eligible discounts atomically with row locks (`select_for_update`) and `F()` increments.

#### `InvoiceService.generate_due_invoices(run_date=today)`
- **Module:** `apps.invoicing.services.InvoiceService`
- **Management command:** `python manage.py generate_invoices [--date YYYY-MM-DD] [--dry-run]`
- **Behavior:**
  - Queries subscriptions where `status='ACTIVE'` and `next_billing_date <= run_date`.
  - Processes in batches (`iterator(chunk_size=100)`).
  - Advances `next_billing_date` by `plan.billing_interval` (`DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`) with calendar-accurate month-end handling using `dateutil.relativedelta`.
  - One failing subscription does not stop the batch; returns a summary dictionary with counts of created, skipped, and failed billings.

---

## 2. `Invoice` Model Fields & Properties

Key model fields on `invoicing.Invoice` used by Dashboard, Analytics, and Payments:

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `BigAutoField` | Primary key |
| `invoice_number` | `CharField(64)` | Auto-generated unique reference (e.g., `INV-2026-000123`) |
| `customer` | `FK('accounts.CustomerProfile')` | Customer billed |
| `subscription` | `FK('subscriptions.Subscription')` | Associated subscription (nullable) |
| `subtotal` | `Decimal(12, 2)` | Pre-discount, pre-tax subtotal |
| `discount_amount` | `Decimal(12, 2)` | Net discount deducted |
| `tax_amount` | `Decimal(12, 2)` | Aggregate tax applied |
| `total_amount` | `Decimal(12, 2)` | **Total final payable amount** |
| `status` | `CharField` | `DRAFT`, `CONFIRMED`, `PAID`, `CANCELLED` |
| `issue_date` | `DateField` | Invoice creation date |
| `due_date` | `DateField` | Calculated deadline from `subscription.payment_terms` |
| `billing_period_start` | `DateField` | Billing cycle start |
| `billing_period_end` | `DateField` | Billing cycle end |

### Helper Properties:
- `invoice.is_paid`: Boolean check if `status == 'PAID'`.
- `invoice.is_overdue`: Boolean check if unpaid and past `due_date`.
- `invoice.can_mark_paid`: `True` if `status in ('DRAFT', 'CONFIRMED')`.
- `invoice.can_cancel`: `True` if `status in ('DRAFT', 'CONFIRMED')` (`PAID` cannot be cancelled).

### Reverse Relations:
- `invoice.lines.all()`: Snapshotted `InvoiceLine` items.
- `invoice.tax_lines.all()`: Itemized `InvoiceTaxLine` breakdown.
- `invoice.discount_usages.all()`: Audit trail of applied `DiscountUsage`.
- `invoice.payments.all()`: Payments attached by Member 4.

---

## 3. Assumptions About Other Members' Apps

Temporary stubs have been provided in `apps/` with initial migrations so this branch can run independently:

1. **Member 1 (`accounts`)**:
   - `AUTH_USER_MODEL = 'accounts.User'` with roles: `ADMIN`, `STAFF`, `CUSTOMER`.
   - `accounts.CustomerProfile`: OneToOne relation with `User`, containing `billing_email`, `billing_address`, and optional `tax_id`.

2. **Member 2 (`products`, `plans`, `subscriptions`)**:
   - `products.Product`: `name`, `sku`, `unit_price`, `is_active`.
   - `plans.Plan`: `name`, `billing_interval` (`DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`), `billing_interval_count`.
   - `subscriptions.Subscription`: `subscription_number`, `customer` (FK `CustomerProfile`), `plan` (FK `Plan`), `start_date`, `expiry_date`, `next_billing_date`, `payment_terms` (integer days), `status` (`ACTIVE`, `PAUSED`, `EXPIRED`, `CANCELLED`).
   - `subscriptions.SubscriptionLine`: `subscription`, `product`, `quantity`, `unit_price`, `tax_rate`, `amount`.

3. **Member 4 (`payments`)**:
   - `payments.Payment`: ForeignKey to `invoicing.Invoice`.

---

## 4. Useful Commands

```powershell
# Run migrations
python manage.py migrate

# Seed sample discounts, taxes, and demo subscriptions
python manage.py seed_discounts_and_taxes

# Dry-run recurring invoice generation
python manage.py generate_invoices --dry-run

# Run automated test suite
python manage.py test
```

