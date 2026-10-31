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

**Invoice emails.** Each invoice can be emailed as a PDF with one click from the invoice page. A daily job (`python manage.py send_invoice_reminders`, run by the `scheduler` container) emails every confirmed invoice that has not been sent, sends a reminder a few days before the due date, and chases overdue invoices every week. Staff can trigger the same run from the Billing Run page.

**Billing day.** The billing run (button on the invoices page, or `python manage.py generate_invoices` on a schedule) creates one draft invoice per due period from each subscription, with customer details, lines, taxes and totals filled in. A unique constraint on subscription and period prevents double billing, and missed periods are caught up so none are skipped. Staff confirm, cancel, send or print any invoice; invoices move Draft, Confirmed, Paid.

**A customer asks for a better price.** Only admins create discounts: fixed or percentage, with minimum purchase or quantity, start and end dates, and a usage limit, scoped to specific products or the whole subscription. The best valid discount is applied automatically on the next invoice and stops when it expires or runs out.

**The money comes in.** Staff record payments against confirmed invoices with method, amount, date and a note. Customers can also pay a confirmed invoice online through Razorpay; the payment is recorded automatically once Razorpay confirms it. The invoice list shows what is paid, outstanding and overdue.

**The finance lead, at the end of the month.** The dashboard shows active subscriptions, revenue received, what is still owed, overdue invoices and payments, filtered by date range, payment method and customer. List pages use annotated queries, indexes and pagination and stay well under two seconds with thousands of subscriptions.

## Run with Docker (PostgreSQL)

```bash
cp .env.example .env
docker compose up --build
```

Open http://localhost:8000/ and sign in with the `ADMIN_USER` email and `ADMIN_PASS` password from `.env`. The web container waits for PostgreSQL, applies migrations, creates or updates the admin account from those two variables, and then serves the app with gunicorn. Static files are served by WhiteNoise. Set `SEED_DEMO=true` in `.env` to load the demo data on first start.

| Variable | Required | Purpose |
| --- | --- | --- |
| `ADMIN_USER` | yes | Email of the admin account created on start |
| `ADMIN_PASS` | yes | Its password, which must follow the password rule |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | no | Database name and credentials, default `brightloop` |
| `DJANGO_SECRET_KEY` | production | Secret key |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | production | Comma-separated host names and origins |
| `WEB_PORT` | no | Host port, default 8000 |
| `SEED_DEMO` | no | `true` to seed demo data |

Run the billing job inside the container on a schedule:

```bash
docker compose exec web python manage.py generate_invoices
docker compose exec web python manage.py send_invoice_reminders
```

The `scheduler` service in Compose already runs both once a day. After editing `.env`, run `docker compose up -d` again so the containers pick up the new values.

## Sending email through Gmail

1. In your Google account turn on 2-Step Verification, then open **Security → App passwords** and create one for "Mail". Google shows a 16-character password.
2. Set these in `.env` (or the environment):

```
EMAIL_HOST_USER=yourname@gmail.com
EMAIL_HOST_PASSWORD=the-16-character-app-password
DEFAULT_FROM_EMAIL=yourname@gmail.com
```

Enter the app password as its 16 letters only, with no spaces or hyphens. Gmail does not return an error for a wrong password; it closes the connection, which shows up as "Connection unexpectedly closed". Check the setup at any time with:

```bash
python manage.py send_test_email you@gmail.com
docker compose exec web python manage.py send_test_email you@gmail.com
```

When both `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` are set the app switches from the console backend to SMTP (`smtp.gmail.com`, port 587, TLS). Leave them unset in development and every email, including the PDF attachment, prints to the terminal instead. Your normal Google password will not work; Gmail requires an app password for SMTP.

`INVOICE_REMINDER_DAYS_BEFORE` (default 3) controls how many days before the due date the first reminder goes out, and `INVOICE_REMINDER_REPEAT_DAYS` (default 7) how often overdue invoices are chased.

## Online payments with Razorpay (test mode)

1. Create a Razorpay account and copy the **test** key id and secret from Settings → API Keys.
2. Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `.env` (or the environment). The **Pay now** button appears on confirmed invoices for customers only when both are set.
3. Optionally add a webhook in the Razorpay dashboard pointing to `https://your-host/payments/razorpay/webhook/` for the `payment.captured` and `payment.failed` events, and put its secret in `RAZORPAY_WEBHOOK_SECRET`. The webhook records payments the browser failed to report back.

In test mode use Razorpay's test cards, for example `4111 1111 1111 1111` with any future expiry and CVV, or the `success@razorpay` UPI id.

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
python manage.py send_invoice_reminders [--date YYYY-MM-DD]          # email unsent, due and overdue invoices with PDF
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | insecure dev key | Secret key |
| `DJANGO_DEBUG` | `True` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated hosts |
| `DATABASE_URL` | SQLite file | Any `dj-database-url` URL; Compose sets a PostgreSQL URL |
| `ADMIN_USER`, `ADMIN_PASS` | | Admin account created by `python manage.py ensure_admin` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | | Comma-separated origins when served behind a domain |
| `DJANGO_EMAIL_BACKEND` | console | Email backend for invoices and password resets |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | | SMTP settings |
| `DEFAULT_FROM_EMAIL` | `billing@brightloopsoftware.com` | Sender address |
