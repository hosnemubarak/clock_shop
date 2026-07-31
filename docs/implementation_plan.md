# Implementation Plan

Single source of truth for implementation progress on the Clock Shop inventory / POS project.
Every entry names the file (and function) it applies to, so the checklist can be re-verified
against the code rather than trusted on faith.

Legend: `- [x]` done and verified · `- [ ]` open

Last updated: 2026-07-31

## Progress summary

| # | Section | Done | Open |
|---|---------|------|------|
| 1 | Critical write paths & transactions | 11 | 0 |
| 2 | Money math & reporting accuracy | 7 | 0 |
| 3 | Timezone correctness | 11 | 0 |
| 4 | Settings, security & deployment | 11 | 1 |
| 5 | Tests | 5 | 0 |
| 6 | Code hygiene / dead code | 13 | 0 |
| 7 | Awaiting decision | 0 | 5 |
| | **Total** | **58** | **6** |

Every open item is either a decision for the project owner (section 7) or explicitly
deferred pending one (section 4). No code defect from the review is knowingly left open.

## 1. Critical write paths & transactions

- [x] Make stock-out completion transactional and row-locked (`apps/inventory/models.py`: `StockOut.complete_stockout`)
- [x] Wrap product creation with initial stock in one transaction (`apps/inventory/views.py`: `product_create`)
- [x] Wrap purchase creation + stock/WAC updates in one transaction (`apps/inventory/views.py`: `purchase_create`)
- [x] Wrap quick stock-add in one transaction with row locks (`apps/inventory/views.py`: `api_quick_add_stock`)
- [x] Pre-validate then transact on stock transfers (`apps/warehouse/views.py`: `transfer_create`)
- [x] Lock stock rows in `product_id` order to remove deadlock risk (`apps/inventory/models.py`: `complete_stockout`, `cancel_stockout`)
- [x] Make POS sale creation self-atomic so a caught `ValueError` rolls back (`apps/sales/services.py`: `SaleService.create_from_pos`)
- [x] Coerce/validate the whole POS cart before any write, so bad payloads return 400 not 500 (`apps/sales/services.py`: `_to_decimal`, `_to_int`)
- [x] Move `sale_create` writes into an explicit `atomic()` block with the `ValueError` caught outside it, replacing manual `sale.delete()` compensation (`apps/sales/views.py`: `sale_create`)
- [x] Raise on unknown product IDs instead of silently skipping the line item (`apps/sales/views.py`: `sale_create`)
- [x] Lock POS/sale stock rows in a stable order (`apps/sales/services.py`, `apps/sales/views.py`)

Verified: five POS failure modes (over-sell, non-numeric quantity, missing price,
unknown product, malformed decimal) each return a readable `ValueError` and leave zero
orphaned `Sale` rows and zero stock drift.

## 2. Money math & reporting accuracy

- [x] Exclude cancelled sales from dashboard revenue (`apps/core/views.py`: `dashboard`)
- [x] Fix double-counted discount in profit (`apps/sales/models.py`: `Sale.profit`)
- [x] Apply tax after discount so invoices do not under-charge (`apps/sales/views.py`: `sale_create`)
- [x] Filter revenue/profit aggregates to completed sales (`apps/reports/views.py`)
- [x] Recompute customer balances from payments and sales (`apps/customers/views.py`)
- [x] Correct payment-status derivation (`apps/sales/management/commands/fix_sale_payments.py`)
- [x] Use weighted average cost in the correct order: WAC before `update_total_stock()` (`apps/inventory/models.py`)

## 3. Timezone correctness

- [x] Set `TIME_ZONE` to `Asia/Dhaka`, env-overridable (`clock_shop/settings.py`)
- [x] Fix the daily invoice/purchase number prefix, which put two Dhaka business days on one series (`apps/core/utils.py`: `save_with_sequential_number`)
- [x] Licence-expiry countdown uses `timezone.localdate()` (`apps/core/context_processors.py`)
- [x] Report date ranges use `timezone.localdate()` — 4 sites (`apps/reports/views.py`)
- [x] Sale form default date uses `timezone.localdate()` (`apps/sales/views.py`: `sale_create`)
- [x] POS sale date falls back to `timezone.localdate()` (`apps/sales/services.py`)
- [x] Test fixture uses `timezone.localdate()` (`apps/inventory/tests/test_models.py`)
- [x] Move each `datetime` import in the same edit as its call site, avoiding the `NameError` class of regression
- [x] Confirm no naive `date.today()` / `timezone.now().date()` remains in `apps/` or `clock_shop/`
- [x] Verify at runtime that `localtime` reports `+06` and a fresh invoice carries the Dhaka date
- [x] Fix `TruncDate` on `DateField` crash (`apps/reports/views.py`: `sales_report`) — group day mode on `F('sale_date')` instead of `TruncDate`, avoiding the SQLite UDF `AttributeError` once `TIME_ZONE != 'UTC'`

## 4. Settings, security & deployment

- [x] List explicit ports in `CSRF_TRUSTED_ORIGINS` — Django wildcards the host, never the port, so the old `:*` defaults were inert (`clock_shop/settings.py`)
- [x] Add the `i18n` context processor so `{{ LANGUAGE_CODE }}` renders (`clock_shop/settings.py`)
- [x] Migrate `STATICFILES_STORAGE` to the `STORAGES` dict — the old setting was silently ignored on Django 5.1+ (`clock_shop/settings.py`)
- [x] Add `CONN_MAX_AGE` and `CONN_HEALTH_CHECKS` to all four database branches (`clock_shop/settings.py`)
- [x] Delete six `LOGGING` children byte-identical to their `apps` parent (`clock_shop/settings.py`)
- [x] Remove the `request` log formatter referenced by no handler (`clock_shop/settings.py`)
- [x] Keep `SECRET_KEY` production guard and HSTS/SSL block intact (`clock_shop/settings.py`)
- [x] Cache the `SystemSettings` singleton with invalidation on save, removing a query per template render (`apps/core/models.py`: `get_settings`)
- [x] Treat a configured threshold of `0` as valid rather than unset (`apps/core/context_processors.py`)
- [x] Default `alert_days_before_expiry` without swallowing `0` (`apps/core/context_processors.py`)
- [x] Verify `/health/` responds 200 unauthenticated (`clock_shop/urls.py`)
- [ ] Gate the media `serve()` mount on `DEBUG` (`clock_shop/urls.py:27-29`) — the comment at lines 25-26 shows the unconditional mount was deliberate, so this needs the owner's call, not an assumption

## 5. Tests

- [x] Fix 6 `NoReverseMatch` errors caused by namespaced URLconfs (`app_name` in every app)
- [x] Fix `test_sale_creation` posting a datetime into a `DateField`
- [x] Consolidate scattered `tests.py` files into per-app `tests/` packages
- [x] Add a regression test covering all three `sales_report` groupings under a non-UTC `TIME_ZONE` (`apps/reports/tests/test_views.py`: `test_sales_report_groupings_with_non_utc_timezone`)
- [x] Full suite green: `Ran 20 tests ... OK`, `manage.py check` clean

## 6. Code hygiene / dead code

- [x] Add a module logger and log the swallowed exception instead of discarding it (`apps/sales/views.py`: `pos_checkout`)
- [x] Delete 8 dead re-imports inside `pos_checkout`, keeping the deliberate `SaleService` local import (`apps/sales/views.py`)
- [x] Drop unused `F`, `datetime`, and a `Warehouse` re-import (`apps/sales/views.py`)
- [x] Drop unused `datetime` and `IntegrityError` (`apps/inventory/models.py`)
- [x] Fix the `StockOut.REASON_CHOICES` attribute error that crashed `stockout_list` on every request (`apps/inventory/views.py`)
- [x] Use the nested `Status` `TextChoices` instead of raw status strings (`apps/inventory/models.py`)
- [x] Guard the nullable `StockOutItem.product` dereference (`apps/inventory/models.py`: `__str__`)
- [x] Remove the N+1 in POS stock updates by reusing the prefetched product map (`apps/sales/services.py`)
- [x] Avoid `select_related` on locked querysets, which would also lock joined product rows (`apps/sales/services.py`)
- [x] Delete the unused `StockTransferItemForm` and its three now-orphaned imports (`apps/warehouse/forms.py`)
- [x] Collapse the duplicated warehouse-stocks endpoint onto the inventory superset (`apps/warehouse/views.py`: `api_warehouse_stocks`)
- [x] Emit both `product_name` and `product_sku` so both consuming templates keep working (`apps/inventory/views.py`)
- [x] Tidy decorators and shared helpers (`apps/core/decorators.py`, `apps/core/utils.py`)

## 7. Awaiting decision

These are blocked on the project owner, not on code. Nothing here has been actioned.

- [ ] **Run migration `sales/0006_repair_sale_status_and_balances`?** Written and still unapplied. It rewrites persisted financial data: illegal `Sale.status` values `paid`/`partial` become `completed`, and `paid_amount`, `payment_status` and customer balances are recomputed. Idempotent, reverse is a no-op. Not run against any real database without a green light. Note `entrypoint.sh:31` runs `migrate --noinput`, so starting the docker-compose stack applies it too.
- [ ] **Role enforcement policy.** The fifth critical review finding. Needs a decision on which roles may void sales, record payments, edit cost prices, transfer stock, and read audit logs before it can be implemented.
- [ ] **`requirements.txt` pins `Django==4.2.11` but the runtime is 6.0.6.** Re-pin to the installed version, or install the pin? Deployment-affecting.
- [ ] **Delete `apps/reports/views_original.py`?** ~50 KB, untracked, looks like a dead backup. Still holds four naive-date call sites, deliberately left alone.
- [ ] **Remove or wire up the vestigial payment-status dashboard chart?** JS at `templates/core/dashboard.html:344-395`, ApexCharts CDN tag at line 323, counts at `apps/core/views.py:86-101`, plus unused `profit_month` / `total_customers` context keys.

## Verification method

Re-runnable checks behind the boxes above:

```bash
python manage.py check && python manage.py test apps
```

Runtime checks performed against the `django-dev` preview server on port 8000: `/health/`
returns 200; the dashboard, POS, sales, sale form, products, stock-out, warehouse, customers,
reports, settings and audit-log pages all render 200 with no console errors; both
warehouse-stock API shapes verified. POS write-path scenarios were exercised inside an outer
transaction that was rolled back, so the development database was left unchanged (confirmed
afterwards: 5 sales, stock unchanged).
