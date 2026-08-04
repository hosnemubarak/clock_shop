# Clock Shop — Comprehensive Project & Production-Readiness Review

**Project:** `clock_shop` (Django 4.2 retail POS / inventory system)
**Scope:** Business logic (sales, purchases, inventory, customers, suppliers, payments, returns, reports, settings), security, performance, data integrity, and cPanel production readiness.
**Verdict:** **NOT production-ready.** Deployment on cPanel will fail as configured, and role-based access control is not enforced. See the prioritized action plan at the end.

---

## 1. Executive Summary

The codebase is well-structured and, in isolated areas, unusually careful: the sale-return/refund ledger, weighted-average-cost (WAC) updates, and stock-movement concurrency (`select_for_update` with stable lock ordering) are correctly implemented and backed by thorough tests (`apps/sales/tests/test_returns.py`, `test_payments.py`). Transactions wrap multi-row writes, and payloads are coerced before DB writes.

However, the project has **blocking deployment gaps** and **one critical business-logic/security gap**:

- **Role-Based Access Control (RBAC) is defined but never applied.** `admin_required` / `manager_required` / `cashier_required` exist in `apps/core/decorators.py`, and `setup_roles` creates the groups, but **no view uses them**. Every authenticated, approved user can cancel sales, issue refunds, delete products, adjust stock, and read all financial reports and audit logs.
- **cPanel deployment cannot succeed as shipped:** no `passenger_wsgi.py`, the only DB driver in `requirements.txt` is `psycopg2-binary` while the guide/prerequisites contradict themselves (PostgreSQL vs MySQL), and the runtime config (`entrypoint.sh` + Gunicorn) is Docker-only.
- **Per-process `LocMemCache`** breaks the registration rate-limiter and `SystemSettings` consistency once Passenger spawns multiple processes.
- **Refund/credit-limit/overpayment business rules are unenforced or inconsistent** across entry points.

The application is a strong internal build but needs the fixes below before it is safe to expose in production.

---

## 2. Business Logic Review Findings

### CRITICAL

**BL-C1 — RBAC not enforced anywhere.**
`apps/core/decorators.py:12-14` defines role decorators; `apps/core/management/commands/setup_roles.py` creates `Admin/Manager/Cashier`. A codebase-wide search shows **zero usages** — every view is guarded only by `@login_required`. Consequences: a cashier can cancel completed sales (`sales/views.py:sale_cancel`), issue cash refunds (`return_create`), delete products/brands/categories, run stock-outs, change warehouses, and view profit/audit data. Only `core:system_settings` is superuser-gated. This is both a business-control failure and a security failure.

**BL-C2 — Refund amount is not bounded by what was actually paid.**
`return_create` (`sales/views.py:436-463`) accepts any non-negative `refund_amount` and calls `reconcile_sale_ledger`, which reduces `paid_amount` floored at 0 but does **not** cap the refund at `sale.paid_amount` or at returned-goods value. A user can refund more cash than the customer ever paid. `customer.recalculate_balance()` can then drive `total_due` negative (untracked store credit / cash leakage). No approval step.

### HIGH

**BL-H1 — POS/customer payments allow uncapped overpayment; enforcement is inconsistent.**
`SaleService.create_from_pos` (`sales/services.py:191-201`) records any `payment_amount` with no check against `total_amount`. `customers/views.py:payment_create` likewise records arbitrary amounts. Only `sales/views.py:sale_payment` caps at `due_amount`. Overpayment produces `paid_amount > total_amount`, negative `due_amount`, and negative `customer.total_due` — an "advance/credit" concept that is not modeled, reported, or reconciled.

**BL-H2 — Payments/returns are allowed against cancelled sales via direct POST.**
`sale_payment` does not check `sale.status`. A payment can be recorded on a cancelled sale; `recalculate_paid_amount` updates the sale, but `customer.recalculate_balance()` excludes cancelled sales, so recorded cash silently disappears from the ledger. Return creation checks status, payment does not.

**BL-H3 — Customer `credit_limit` is never enforced.**
`Customer.credit_limit` exists but no sale/checkout path validates outstanding due + new credit sale against it. Credit sales are unbounded.

**BL-H4 — SaleItem-level report aggregates are not net of returns.**
Returns reduce `Sale.total_amount`/`total_cost` (via `reconcile_sale_ledger`) but do **not** reduce `SaleItem.quantity`. Reports that aggregate on `SaleItem` overstate results after returns:
- Dashboard `profit_month` (`core/views.py:42-47`)
- `sales_report` "Top selling products" (`reports/views.py:98-110`)
- `profit_report` profit-by-product/category/warehouse (`reports/views.py:235-296`)
- `customer_detail` product summary (`customers/views.py:86-94`)

Sale-level totals in `sales_report` summary are correct, so the same page can show internally inconsistent numbers.

### MEDIUM

**BL-M1 — Low-stock threshold is hardcoded in places, configurable in others.**
`SystemSettings.low_stock_threshold` (default 5) drives the dashboard, but `inventory/views.py:47` and `reports/views.py:408,461` hardcode `<= 10`. Users changing the setting will see contradictory "low stock" lists.

**BL-M2 — Model validators do not fire on `create()/save()`.**
`MinValueValidator`s on money/quantity fields only run through `full_clean()`, which the service/view paths mostly bypass. Negative amounts are prevented only by ad-hoc checks in `services.py`; admin edits and other code paths can persist invalid values. `Sale.calculate_totals` can produce a negative `total_amount` if `discount_amount > subtotal` (the guard exists only in `services.py:183`).

**BL-M3 — Payments cannot be backdated; statement ordering is ambiguous.**
`Payment.payment_date` is `auto_now_add` (immutable). `customer_statement` normalizes payments to date only and sorts by date, so a same-day payment can sort before its invoice, making the running balance momentarily incorrect. `sale_date` is a `DateField` (no time), compounding same-day ordering.

**BL-M4 — No enforced single "shop" warehouse at the DB level.**
`Warehouse.set_as_shop()` enforces one shop in app code only. Direct admin edits can create two `is_shop=True` rows; POS then uses `.filter(is_shop=True).first()` (non-deterministic). No partial unique constraint.

### LOW

- **BL-L1** — `SaleReturnItem.__str__` (`sales/models.py:312`) dereferences `sale_item.product.display_name`; crashes for custom (product-less) line items.
- **BL-L2** — Dead/aspirational code: `SaleItemForm`, `QuickSaleForm`, `QuickPaymentForm`, `StockAdjustmentForm`, `PurchaseItemForm`, and `_customer_loyalty` (reads non-existent `loyalty_*` attributes).
- **BL-L3** — "Supplier" is a free-text `CharField` on `Purchase`/StockOut, not a first-class entity; no supplier ledger, dedup, or return-to-supplier accounting despite the review scope mentioning suppliers.
- **BL-L4** — Sequential number generator (`core/utils.py:save_with_sequential_number`) relies on read-then-write + unique constraint + 10 retries; correct but can exhaust retries under very high concurrency.

---

## 3. Security Review

- **RBAC absent** (see BL-C1) — highest-impact security finding.
- **Audit logs readable by any authenticated user** (`core/views.py:audit_logs` is `@login_required` only).
- **Registration hardening is weak:** custom `register` view bypasses `UserCreationForm`, so `AUTH_PASSWORD_VALIDATORS` do **not** apply — only an inline 8-char check runs. Rate-limiting uses `LocMemCache` keyed on `REMOTE_ADDR`, so it is per-process (ineffective across Passenger workers) and keyed on the proxy IP behind cPanel/Apache.
- **Committed environment/data artifacts:** `.env.cpanel` is tracked and contains the real cPanel account prefix (`rumaelec_...`) — hosting-account and DB-naming disclosure. `dump.sql.gz` is tracked (currently 0 bytes) and should not live in the repo.
- **`SECRET_KEY`** has an insecure default; guarded so production with `DEBUG=False` refuses the default (good). Ensure `DEBUG` can never be flipped true in prod.
- **`SECURE_PROXY_SSL_HEADER`** is trusted unconditionally in prod; combined with `SECURE_SSL_REDIRECT` this causes a redirect loop if Apache does not set `X-Forwarded-Proto`, and is spoofable if the app is ever reachable without the proxy.
- **Missing hardening headers:** `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY` not set (defaults vary by Django version — set explicitly).
- **Media served through Django** `serve()` in all environments (`clock_shop/urls.py:27-28`) — unauthenticated and unoptimized.
- **No login throttling / account lockout** (Django default).
- Positive: CSRF middleware enabled, `CSRF_TRUSTED_ORIGINS` env-driven, secure cookies + HSTS in prod, `X-Frame-Options` middleware present, no `|safe`/`mark_safe`/`autoescape off` in templates (XSS surface low), parameterized ORM (no raw SQL).

---

## 4. Performance & Scalability Review

- **`LocMemCache` is per-process.** Under Passenger (multiple processes) `SystemSettings` cache is inconsistent and the registration rate-limiter is effectively bypassed. Use `DatabaseCache` (+ `createcachetable`) or a file-based cache.
- **`CONN_MAX_AGE=60` persistent connections** multiply by the number of Passenger processes; shared-host DB connection limits can be exhausted. On shared cPanel prefer `CONN_MAX_AGE=0`.
- **Unbounded in-Python aggregation:** `customer_statement` loads all sales + payments and sorts in Python (no pagination) — slow for large customers. `profit_report`/`stock_report` Excel exports iterate the full result set (no 10k cap that `sales_report` has) — memory/timeout risk on large catalogs.
- **PDF generation via `xhtml2pdf`** is CPU-heavy; large reports can exceed Passenger request timeouts.
- **Missing indexes** for frequent filters: `Sale.status`, `Sale.payment_status`, `ProductStock.quantity`, and common report composites. `sale_date`, `payment_date`, `AuditLog.timestamp` are indexed (good).
- **Per-shop loop queries** in `sales_report` (one aggregate per shop) — acceptable for few shops, scales linearly.

---

## 5. Data Integrity & Validation Review

- **Heavy reliance on denormalized fields** (`Product.total_stock`, `average_cost`; `Customer.total_purchases/paid/due`; `Sale.subtotal/total_amount/total_cost/paid_amount`) recomputed via signals. Any path that bypasses the signal/recalc drifts. The existence of `apps/sales/management/commands/fix_sale_payments.py` indicates prior drift. There is no scheduled reconciliation job.
- **No DB-level CHECK constraints** (e.g., `paid_amount <= total_amount`, `refund <= paid`, single `is_shop`). Integrity depends entirely on app code.
- **Over-refund possible** (BL-C2); **overpayment possible** (BL-H1); **payment on cancelled sale possible** (BL-H2).
- **Validators bypassed on save** (BL-M2).
- Positive: unique constraints on SKU, invoice/PO/transfer/return numbers, customer phone, and partial-unique customer email; `on_delete=PROTECT` guards historical references; stock movements are transactional and row-locked.

---

## 6. Production Readiness Assessment (cPanel)

**Blockers**
1. **No `passenger_wsgi.py`.** cPanel "Setup Python App" runs under Phusion Passenger and needs a `passenger_wsgi.py` shim (importing `clock_shop.wsgi.application`). `entrypoint.sh`/Gunicorn are Docker-only and will not run on cPanel. The app will not boot.
2. **Database driver mismatch.** `requirements.txt` ships only `psycopg2-binary`. The guide's prerequisites say "MySQL database access," the title/steps say PostgreSQL, and the closing line says MySQL. Typical shared cPanel offers **MySQL** only; the MySQL branch in `settings.py` requires `mysqlclient`/`PyMySQL`, which is **absent** → `ImportError` at startup.

**Major**
3. **`LocMemCache`** breaks rate-limiting/settings across Passenger processes (see §4).
4. **File logging under multiple processes:** `RotatingFileHandler` writing shared `logs/*.log` from concurrent Passenger processes can race on rotation/corrupt logs. Prefer a single non-rotating file or `WatchedFileHandler`, or per-process filenames.
5. **Media handling** relies on Django `serve()`; the guide's better path (Apache symlinks) is optional and not wired by default.
6. **No email backend / `ADMINS`:** password reset, approval notifications, and `mail_admins` error reporting are non-functional.
7. **Docs are inconsistent and reference missing artifacts:** duplicated Steps 5 & 6, MySQL-vs-PostgreSQL contradictions, references to `passenger_wsgi.py` and `.htaccess` gzip that do not exist in the repo, and `mysqlclient` install notes with no corresponding requirement.

**OK / Positive**
- `DEBUG=False` enforced with secret-key guard; HSTS/secure cookies/SSL redirect configured for prod.
- WhiteNoise `CompressedStaticFilesStorage` for static files; `collectstatic` documented.
- `/health/` endpoint present; timezone `Asia/Dhaka`, `USE_TZ=True`.
- `.env` is git-ignored.

---

## 7. Deployment Risks & Recommendations

| Risk | Impact | Recommendation |
|---|---|---|
| Missing `passenger_wsgi.py` | App won't start | Add a `passenger_wsgi.py` importing `application` from `clock_shop.wsgi`. |
| Missing MySQL driver | Startup ImportError on MySQL hosts | Add `mysqlclient` (or `PyMySQL` shim) to `requirements.txt`; confirm whether the host offers PostgreSQL or MySQL and pick one path. |
| `LocMemCache` multi-process | Broken rate-limit / stale settings | Switch to `DatabaseCache` (+ `createcachetable`) or file cache. |
| `CONN_MAX_AGE=60` × N processes | DB connection exhaustion | Set `CONN_MAX_AGE=0` on shared cPanel. |
| Rotating file logs across processes | Corrupt/rotation races | Use `WatchedFileHandler` or per-process log files; or log to stderr for Passenger. |
| `SECURE_SSL_REDIRECT` + proxy header | Redirect loop if Apache omits header | Verify Apache passes `X-Forwarded-Proto`; otherwise gate redirect. |
| Committed `.env.cpanel` / `dump.sql.gz` | Info disclosure / repo hygiene | Untrack both; scrub account-specific values; keep only sanitized templates. |
| Report export size | Memory/timeout | Cap export rows; paginate `customer_statement`; consider async/streamed exports. |
| No automated backups | Data loss | Add scheduled `pg_dump`/`mysqldump` cron + off-site copy; remove repo dump. |

---

## 8. Code Quality & Maintainability Review

**Strengths**
- Clear app separation; transactional, row-locked stock movements with documented lock ordering to avoid deadlocks.
- Extensive, meaningful comments capturing the rationale behind past fixes.
- Genuinely good test coverage for the hardest logic (returns/refunds/payments ledger, restock, double-restock prevention).
- POS creation extracted into a testable `SaleService`.

**Weaknesses**
- **Inconsistent placement of business rules:** POS logic in a service, but returns/payment/cancel logic in views — harder to test and reuse; refund/overpayment caps live in some paths only.
- **Validation split** between service-level ad-hoc checks and (bypassed) model validators; no single source of truth.
- **Dead code** (unused forms, loyalty stub) and **magic numbers** (hardcoded `10` thresholds).
- **Documentation drift** in the cPanel guide (duplicate steps, DB engine contradictions, references to non-existent files).
- Denormalized-field pattern without a reconciliation/consistency job.

---

## 9. Prioritized Action Plan (required before production)

> This is a review deliverable; implementing the code changes below requires an implementation-capable agent (source edits + migrations).

### P0 — Blockers (must fix before any deploy)
1. **Add `passenger_wsgi.py`** at project root importing `clock_shop.wsgi.application`; verify boot under cPanel "Setup Python App".
2. **Resolve the DB engine + driver:** decide PostgreSQL vs MySQL for the target host; add the matching driver to `requirements.txt` (`mysqlclient`/`PyMySQL` if MySQL). Make the cPanel guide internally consistent.
3. **Enforce RBAC:** apply `admin_required`/`manager_required`/`cashier_required` (and superuser gates for audit logs) to every mutating and financial view; add tests asserting a cashier cannot cancel sales, delete products, refund, or view audit logs/reports.
4. **Switch cache off `LocMemCache`** to `DatabaseCache` (run `createcachetable`) or a file cache; re-verify registration throttling and `SystemSettings` consistency.
5. **Untrack secrets/artifacts:** `git rm --cached .env.cpanel dump.sql.gz`; scrub account-specific values; keep sanitized templates only.

### P1 — Critical business/data-integrity fixes
6. **Cap refunds** at `min(sale.paid_amount, returned_goods_value)`; block refunds that would push customer balance negative; require manager approval.
7. **Prevent overpayment consistently** (POS + `payment_create`): cap payment at outstanding due, or explicitly model store credit/advances and report it.
8. **Block payments/returns on cancelled sales** (check `sale.status` in `sale_payment` and payment paths).
9. **Make report aggregates net of returns** (dashboard profit, top products, profit-by-*, customer product summary) — reduce returned quantities or aggregate from return-adjusted sources.
10. **Add a `select_for_update` lock on the sale** in `sale_payment` to close the overpayment race.

### P2 — Hardening & correctness
11. Enforce `credit_limit` on credit sales.
12. Centralize thresholds on `SystemSettings.low_stock_threshold` (remove hardcoded `10`s).
13. Add DB constraints: single `is_shop=True` (partial unique), `paid_amount <= total_amount` where applicable, `refund <= paid`; call `full_clean()` or add validation on save paths.
14. Fix `SaleReturnItem.__str__` for custom items; remove dead code.
15. Configure email backend + `ADMINS`/`mail_admins`; wire password reset and approval notifications.
16. Set `CONN_MAX_AGE=0` (shared host), switch to `WatchedFileHandler`/stderr logging, verify `X-Forwarded-Proto` handling to avoid redirect loops.
17. Add missing indexes (`Sale.status`, `Sale.payment_status`, report composites); paginate `customer_statement`; cap all report exports.

### P3 — Operability & docs
18. Add a scheduled reconciliation command (extend `fix_sale_payments`) to detect/repair denormalized drift.
19. Automate DB + media backups (cron `pg_dump`/`mysqldump` + off-site); document restore.
20. Rewrite the cPanel guide to match reality (Passenger, chosen DB, static/media symlinks, no `.htaccess`/gzip claims unless added).
21. Run `python manage.py check --deploy`, the full test suite, and a load/export smoke test on a staging cPanel account before go-live.

---

## Open Questions (to confirm before implementation)
1. **Target host DB engine:** does the cPanel plan provide PostgreSQL, or MySQL only? (Drives P0-2.)
2. **Overpayment semantics:** should advances/store credit be a real feature, or strictly capped at due?
3. **Refund policy:** who may approve refunds, and is refunding more than paid ever allowed?
4. **Are suppliers meant to be first-class** (ledger, returns-to-supplier), or is free-text acceptable for now?
