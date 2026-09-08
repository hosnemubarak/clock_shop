# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django 4.2 inventory & sales management system for a retail clock/watch shop (Bangladesh market, BDT `৳`, `Asia/Dhaka` timezone). Server-rendered (Django templates + Invoika/Bootstrap 5 + ApexCharts) — **not** a REST/SPA app, though a handful of internal AJAX JSON endpoints exist for batch/invoice/product lookups.

## Commands

Run everything through the project virtualenv (`.venv/`). Prefix with the venv Python or activate it first.

```bash
# Dev server
python manage.py runserver

# Tests (Django test runner; there is no pytest config)
python manage.py test                                   # whole suite
python manage.py test apps.sales                        # one app
python manage.py test apps.sales.tests.test_views       # one module
python manage.py test apps.sales.tests.test_views.PosCheckoutTests.test_...   # one test
# RBAC is auto-disabled during tests (settings.py checks `'test' in sys.argv`)

# Migrations
python manage.py makemigrations
python manage.py migrate

# First-run / data setup (idempotent management commands)
python manage.py setup_groups              # seed Cashier/Manager/Admin groups + permissions (RBAC depends on this)
python manage.py setup_walkin_customer     # seed the default walk-in customer
python manage.py createcachetable          # DatabaseCache backing table (required — see Caching below)
python manage.py fix_sale_payments         # data-repair command for sale/payment totals

# Background worker (Telegram notifications) — needs Redis running
python manage.py rqworker default

# i18n (English + Bengali `bn`)
python manage.py makemessages -l bn
python manage.py compilemessages

# Static (production)
python manage.py collectstatic --noinput
```

Docker (`docker compose up -d --build`) runs four services: `web` (gunicorn), `db` (Postgres 15), `redis`, and a dedicated `rq_worker`. `entrypoint.sh` waits for the DB then runs `migrate` + `createcachetable` before starting gunicorn.

## Configuration model

- **`clock_shop/settings.py` is env-driven** (via `python-dotenv`, `.env`). It selects the DB engine at runtime: `DATABASE_URL` (any scheme) → `DB_ENGINE=mysql|postgresql` → SQLite default. Same codebase targets SQLite (dev), Postgres (Docker), and MySQL (cPanel/Passenger via `passenger_wsgi.py`).
- **Two settings layers.** OS-env settings (`SECRET_KEY`, DB, `ENABLE_RBAC`, `REDIS_URL`, `NOTIFICATION_MAX_RETRIES`) live in `settings.py`. Business settings (shop name/address/logo, currency symbol, low-stock threshold, license-expiry alerts, avg-cost visibility, walk-in toggle) live in the **`SystemSettings` DB singleton** (`apps/core/models.py`) and **override the env fallbacks**. `apps/core/context_processors.py::global_context` resolves DB-then-env and injects the result into every template — read config there, not from `settings.*`, for these values.
- **Windows:** RQ uses `SimpleWorker` (no `os.fork`), set in `settings.py`.

## Architecture

Eight local apps under `apps/`, each mounted at a URL prefix in `clock_shop/urls.py`: `core` (`/`: dashboard, auth, audit log, system settings), `inventory`, `sales`, `customers`, `warehouse`, `reports`, `quotations`, `notifications`. `django_rq` is mounted at `/django-rq/`.

### Business logic lives in service classes, not views
Write paths are centralized in `apps/*/services.py` (notably `apps/sales/services.py::SaleService.create_from_pos`). Views stay thin and delegate. When adding/changing a sale, stock mutation, or payment, do it in the service layer.

**Critical invariant:** Django field validators (`MinValueValidator`, `choices`, etc.) do **not** fire on `Model.objects.create()` / `bulk_create` / `bulk_update`. The services therefore do all payload coercion and validation by hand (see the `_to_decimal`/`_to_int` helpers and the explicit negative/credit-limit/stock checks in `SaleService`). Preserve this — don't assume the model enforces anything on bulk writes.

### Batch-based inventory & COGS
Each purchase creates a stock batch with its own buy price. A sale records `cost_price` from the product's `average_cost` at sale time and stores `total_cost` on the `Sale`, so profit is computed against captured cost, not live cost. `SaleService.create_from_pos` is the canonical example of the concurrency-safe pattern: `@transaction.atomic`, `select_for_update()` on `ProductStock` rows locked in **sorted id order** (deadlock avoidance), prefetch to avoid N+1, then `bulk_create` items / `bulk_update` stock. Walk-in customers cannot carry a due balance; registered customers are checked against `credit_limit`.

### Notifications: signals → dedup → async → Apprise (fully decoupled, never blocks business ops)
1. `apps/notifications/signals.py` listens to `post_save` on `Sale` and `Payment`, and defers work with `transaction.on_commit` (so nothing sends if the business txn rolls back).
2. `services.notify()` creates one `NotificationLog` row (uniqueness on `(event_type, event_id)` is the event idempotency key) and dispatches the send through **Django-RQ/Redis**. **`notify()` is written to never raise** — a notification failure must never roll back a sale/payment.
3. There is no worker-discovery check or daemon-thread fallback. If Redis/RQ enqueue fails, the durable row remains pending with an error for operational recovery; notification delivery never runs inside a web request.
4. `tasks.send_notification_task` atomically claims a pending row, sends via **Apprise** (Telegram `tgram://`) once, and records `SENT` or `FAILED`. It deliberately does not automatically retry: a provider timeout may mean Telegram accepted the message, so replaying it could duplicate the notification. Telegram creds live in the `TelegramSetting` DB singleton, configured from System Settings UI.

To add a new notification event, mirror this chain (signal → `notify(event_type, event_id, message)`); do not send inline in a view/service.

### RBAC via custom decorators (not Django's mixins)
Authorization is enforced with function decorators in `apps/core/decorators.py`, **not** `PermissionRequiredMixin`. Three role helpers form a hierarchy — `is_cashier` ⊂ `is_manager` ⊂ `is_admin` (`admin_required`/`manager_required`/`cashier_required`) — plus `has_permission('app.codename')` for granular Django permissions. Superusers bypass all checks; when `ENABLE_RBAC=False` (and in tests) every authenticated active user passes. Unauthorized authenticated users are redirected to `core:unauthorized` (or get a JSON 403 for AJAX), never a bare 403. Groups are seeded by `setup_groups`; custom report/dashboard permissions are declared on `SystemSettings.Meta.permissions`.

### Shared core utilities (`apps/core/`)
- `utils.save_with_sequential_number(instance, field, prefix)` — generates per-day document numbers like `INV20260908 0001` with a retry-on-`IntegrityError` loop. Used in model `save()` overrides for invoices, purchases, transfers, etc. **Gotcha:** the sequence is the last 4 digits and resets daily (max 9999 docs/model/day).
- `utils.create_audit_log(request, action, instance, changes)` — writes an `AuditLog` row (`apps/core/models.py`); call it from views on create/update/delete.
- `utils.paginate(request, qs)` and `utils.get_client_ip(request)` — used across list views.
- `TimeStampedModel` — abstract base giving `created_at`/`updated_at`; inherit it for new models.

## Caching

The Django cache backend is **`DatabaseCache`** (chosen for cPanel/Passenger, where Redis isn't available) — Redis is used **only** for the RQ task queue, not the cache. This means `createcachetable` must have run or cache reads/writes error. `SystemSettings.get_settings()` caches the singleton for 60s and invalidates on save.

## Conventions

- Currency is always `৳` (BDT); prices are `DecimalField` — use `Decimal`, never float.
- Media files are served by Django (`re_path` in `urls.py`) even in production.
- Logs are written under `logs/` via rotating handlers split into `app.log` / `error.log` / `security.log` / `db.log`; app code should log under the `apps` logger namespace.
