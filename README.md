# Brightloop Subscription Management System

One Django application that runs the full life of a subscription business as described in the Brightloop brief: products and plans, quotations, subscriptions, recurring invoicing, discounts and taxes, payments, and a finance view, with a customer portal on top.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open http://127.0.0.1:8000/ and sign in with an email. Every demo account uses the password `Brightloop!2026`.

| Email | Role | What they see |
| --- | --- | --- |
| `admin@brightloop.com` | Admin | Everything: products, plans, discounts, taxes, team members, billing |
| `alex@brightloop.com`, `priya@brightloop.com` | Staff | Quotations, subscriptions, invoices, payments, dashboard |
| `ops@apexindustries.com`, `hello@brightcraft.io`, `billing@stellarlogistics.com`, `owner@cornershop.example` | Customer | Their own subscriptions and invoices |

Password reset and invoice emails print to the console in development. Set `DJANGO_EMAIL_BACKEND` and the `EMAIL_*` variables for real delivery.

## How the brief maps to the system

**A new customer signs up.** Registration takes an email and a password. Emails are unique. Passwords must be longer than eight characters with an uppercase letter, a lowercase letter and a special character. A reset link is emailed on request. Admins control the whole system, staff handle day-to-day work, customers see only their own subscriptions and invoices. Only an admin can add a team member.

**Launching a new plan.** Admins add products with name, type, sales price, cost price and notes, and variants that change the price, for example a brand variant adding 560. Each product carries the tax rule that applies to it. Plans define price, billing interval (daily, weekly, monthly, yearly), minimum quantity, availability dates, and whether the plan closes on its own at the end, can be closed early, paused or renewed.

**Turning a quote into a subscription.** Staff start from a quotation template that already holds the plan and product lines and stays valid for a set number of days. A quotation moves Draft, Sent, Confirmed and converts into a subscription. Each subscription has its own number, customer, plan, start and expiry dates, payment terms and lines with product, quantity, unit price, tax and amount, and moves Draft, Quotation, Confirmed, Active, Closed.

**Billing day.** The billing run (button on the invoices page, or `python manage.py generate_invoices` on a schedule) creates one draft invoice per due period from each subscription, with customer details, lines, taxes and totals filled in. A unique constraint on subscription and period prevents double billing, and missed periods are caught up so none are skipped. Staff confirm, cancel, send or print any invoice; invoices move Draft, Confirmed, Paid.

**A customer asks for a better price.** Only admins create discounts: fixed or percentage, with minimum purchase or quantity, start and end dates, and a usage limit, scoped to specific products or the whole subscription. The best valid discount is applied automatically on the next invoice and stops when it expires or runs out.

**The money comes in.** Staff record payments against confirmed invoices with method, amount, date and a note. The invoice list shows what is paid, outstanding and overdue.

**The finance lead, at the end of the month.** The dashboard shows active subscriptions, revenue received, what is still owed, overdue invoices and payments, filtered by date range, payment method and customer. List pages use annotated queries, indexes and pagination and stay well under two seconds with thousands of subscriptions.

## Project layout

```
config/            settings, root URLs, WSGI/ASGI
apps/accounts      users, roles, customer profiles, registration, login, password reset, team members
apps/products      products, variants and tax rules
apps/plans         plans and lifecycle rules
apps/quotations    quotation templates, quotations, conversion to subscriptions
apps/subscriptions subscriptions, lines, lifecycle service
apps/discounts     discount rules and usage tracking
apps/invoicing     invoices, billing run, send and print
apps/payments      payments and outstanding/overdue queries
apps/dashboard     finance summary with filters
templates/         Bootstrap 5 templates (app layout in base.html, sign-in layout in auth_base.html)
static/            stylesheet and shared JavaScript
```

## Commands

```bash
python manage.py test                                              # run the test suite
python manage.py seed_demo                                         # demo users, catalog, quotes, subscriptions, invoices, payments
python manage.py generate_invoices [--date YYYY-MM-DD] [--dry-run] # scheduled billing run
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | insecure dev key | Secret key |
| `DJANGO_DEBUG` | `True` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated hosts |
| `DATABASE_URL` | SQLite file | Any `dj-database-url` URL, for example PostgreSQL |
| `DJANGO_EMAIL_BACKEND` | console | Email backend for invoices and password resets |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | | SMTP settings |
| `DEFAULT_FROM_EMAIL` | `billing@brightloopsoftware.com` | Sender address |
