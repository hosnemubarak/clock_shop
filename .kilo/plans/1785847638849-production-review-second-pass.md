# Clock Shop — Second-Pass Production Review (Verification of Fixes)

**Project:** `clock_shop` (Django retail POS / inventory)
**Scope:** Re-verify every issue from the prior review directly against the code, find regressions/new issues, and decide production readiness.
**Verdict:** **Substantially improved but NOT yet production-ready.** The critical financial/security holes (RBAC, refund/overpayment caps, returns ledger) are genuinely fixed. Several **High** issues remain (credit limit, partial report-netting, RBAC role-assignment lockout, weak password validation) plus deployment-hygiene gaps.

---

## 1. Verification of Prior Findings (evidence-based)

### Confirmed FIXED
- **BL-C1 RBAC enforced.** `admin_required`/`manager_required`/`cashier_required` now decorate views across `sales`, `customers`, `inventory`, `warehouse`, `reports`, and `core`. `ENABLE_RBAC` flag in `settings.py:233`; hierarchy in `apps/core/decorators.py`. `audit_logs` is now `@admin_required` (`core/views.py:125`); `system_settings` still superuser-gated.
- **BL-C2 Refund cap.** `sales/views.py:467-473` caps refund at both `sale.paid_amount` and `returned_goods_value`.
- **BL-H1 Overpayment.** POS caps payment at total (`services.py:187-188`); `sale_payment` caps at `due_amount` under `select_for_update` (`views.py:192-200`); `PaymentForm.clean` caps at `sale.due_amount` (`customers/forms.py:54-65`); `QuickPaymentForm` caps at `total_due`.
- **BL-H2 Payment/return on cancelled sale.** `sale_payment` rejects cancelled (`views.py:184-186`); `PaymentForm.clean` rejects cancelled; `return_create` requires `status == COMPLETED`.
- **Returns ledger correctness.** New `SaleItem.returned_quantity` (migration `0009`), `net_quantity`, and net `total_price`/`total_cost` (`sales/models.py:181-197`). `restock_items` increments `returned_quantity` under a row lock; `reconcile_sale_ledger` recomputes via `calculate_totals()`. No double-counting observed.
- **Deploy blockers.** `passenger_wsgi.py` added; `mysqlclient==2.2.4` added to `requirements.txt`; cache switched to `DatabaseCache` (`settings.py:177-182`); `CONN_MAX_AGE` defaults to `0` (`settings.py:171`).
- **`dump.sql.gz`** no longer tracked by git.

### Partially fixed / still open
- **BL-H4 report netting is incomplete.** Reports (`sales_report`, `profit_report`) now subtract `returned_quantity`, BUT:
  - Dashboard `profit_month` still uses gross `quantity` — `core/views.py:43-48`.
  - `customer_detail` product summary still uses gross `quantity` — `customers/views.py:87-95`.
  These overstate profit/quantities after returns and re-create the same-page inconsistency the fix aimed to remove.
- **BL-M1 hardcoded low-stock `10` remains** in `inventory/views.py:48`, `reports/views.py:409`, `reports/views.py:462`, while the dashboard uses `SystemSettings.low_stock_threshold`. Still contradictory.
- **Secrets: `.env.cpanel` is STILL tracked** (`git ls-files` confirms; not git-ignored). Contains the real cPanel account prefix.

### Confirmed NOT fixed
- **BL-H3 credit limit unenforced.** No sale/checkout path checks `credit_limit` (grep: field + form only). Credit sales remain unbounded.
- **BL-L1 `SaleReturnItem.__str__` crashes for custom items** — `sales/models.py:317-318` dereferences `sale_item.product.display_name` with no null guard.
- **BL-M4 single-shop not enforced at DB level** — only `Warehouse.set_as_shop()` app-code (`warehouse/models.py:27-32`). No partial unique constraint.
- **No DB CHECK constraints** (`paid<=total`, `refund<=paid`).
- **Registration bypasses `AUTH_PASSWORD_VALIDATORS`** — `core/views.py:204-207` only does an inline 8-char check even though validators are configured.
- **Media served via Django `serve()` unconditionally & unauthenticated** — `clock_shop/urls.py:27-29`.
- **Security headers** `SECURE_CONTENT_TYPE_NOSNIFF` / `SECURE_REFERRER_POLICY` not set (grep: none).
- **No email backend / `ADMINS`; no password-reset URL wired** (`core/urls.py` has login/logout/register only).
- **Logging still `RotatingFileHandler`** (`settings.py:272-311`) — rotation races across Passenger processes.
- **BL-M3 payment backdating** unchanged (`Payment.payment_date = auto_now_add`).

---

## 2. New / Newly-surfaced Issues

- **RBAC role-assignment lockout (High).** `setup_roles` only creates the 3 groups; nothing assigns users to a group. With `ENABLE_RBAC=True`, an approved (`is_active=True`) non-superuser in **no** group fails `is_cashier` and is locked out of **every** view including the dashboard. There is no admin UI/command wired to grant roles. This will brick access for normal approved staff.
- **`DatabaseCache` hard dependency (High, operational).** `SystemSettings.get_settings()` runs on every request via the context processor, and `register` uses the cache. If `python manage.py createcachetable` is not run before first request, every page 500s. Documented in the guide (`CPANEL_DEPLOYMENT_GUIDE.md:206,431`) but it is now a single point of total outage.
- **General (no-sale) payment still uncapped (Medium).** `payment_create` with no `sale` selected uses `PaymentForm`, whose cap only triggers when a sale is chosen — a customer-level payment can still exceed `total_due` and drive it negative (store credit remains unmodeled).
- **Stale comment (Low).** `SystemSettings.get_settings()` comment still describes `LocMemCache`/per-process behaviour; cache is now DB-backed and cross-process. Misleading only.

---

## 3. Remaining Issues by Severity

**High**
1. Credit limit unenforced (BL-H3).
2. Dashboard `profit_month` and `customer_detail` product summary not net of returns (BL-H4 remainder).
3. RBAC role-assignment lockout + no automated RBAC tests.
4. Registration bypasses password validators (weak passwords accepted).
5. `.env.cpanel` still committed (secret/account disclosure).

**Medium**
6. Hardcoded `10` low-stock thresholds (BL-M1) in `inventory/views.py:48`, `reports/views.py:409,462`.
7. `SaleReturnItem.__str__` crash for custom items (BL-L1).
8. No DB-level single-`is_shop` / money CHECK constraints (BL-M4).
9. Media served through Django, unauthenticated (`urls.py:27-29`).
10. Missing security headers (`SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY`).
11. No email backend/`ADMINS`; password reset not wired.
12. `RotatingFileHandler` multi-process rotation races (prefer `WatchedFileHandler`/stderr).
13. General no-sale payment not capped vs `total_due`.
14. `createcachetable` must be part of the deploy runbook (outage risk if skipped).

**Low**
15. Stale `LocMemCache` comment in `core/models.py`.
16. `customer_statement` unpaginated in-Python aggregation (perf).
17. Missing indexes on `Sale.status`, `Sale.payment_status`.
18. Dead code (`QuickPaymentForm`, `PurchaseItemForm`, `_customer_loyalty` stub).
19. `SECURE_SSL_REDIRECT` + proxy header unconditional (redirect-loop risk if Apache omits `X-Forwarded-Proto`).
20. `Payment.payment_date` not backdatable (BL-M3).

---

## 4. Ordered Fix Plan (for an implementation-capable agent)

### P0 — before any production deploy
1. **RBAC usability:** add a way to assign roles (extend `setup_roles` to accept `--user`/default group, or wire group selection into the user-approval flow), and document that approved users must belong to a group. Add tests asserting a Cashier cannot cancel sales, delete products, refund, view audit logs/reports; and that a group-less approved user is handled deliberately (not silently locked out).
2. **Untrack secret:** `git rm --cached .env.cpanel`, add to `.gitignore`, rotate the exposed cPanel/DB identifiers, keep only a sanitized template.
3. **Deploy runbook:** make `python manage.py createcachetable` a mandatory, verified step (and `setup_roles`, `collectstatic`, `migrate`, `check --deploy`).

### P1 — correctness & security
4. **Enforce `credit_limit`** on credit (unpaid) sale creation in `SaleService.create_from_pos` and any credit-increasing path; decide policy (block vs. warn) first.
5. **Net dashboard + customer_detail of returns:** change `core/views.py:43-48` and `customers/views.py:87-95` to `F('quantity') - F('returned_quantity')`.
6. **Password validation:** route registration through Django validators (`validate_password`) instead of the inline 8-char check.
7. **Cap no-sale payments** in `payment_create` against `customer.total_due`, or explicitly model advances/store credit.

### P2 — hardening & data integrity
8. Centralize low-stock threshold on `SystemSettings.low_stock_threshold` (remove hardcoded `10` in `inventory/views.py:48`, `reports/views.py:409,462`).
9. Fix `SaleReturnItem.__str__` null-guard for custom items.
10. Add DB constraints: partial-unique single `is_shop`, and `CheckConstraint`s (`paid_amount <= total_amount`, `refund_amount <= paid`).
11. Set `SECURE_CONTENT_TYPE_NOSNIFF = True`, `SECURE_REFERRER_POLICY`; gate/replace media `serve()` (auth-check or Apache/static path); verify `X-Forwarded-Proto` handling.
12. Configure email backend + `ADMINS`; wire password-reset URLs.
13. Switch logging to `WatchedFileHandler` or stderr for Passenger.
14. Add indexes on `Sale.status`, `Sale.payment_status`.

### P3 — operability & cleanup
15. Fix stale cache comment; remove dead code; paginate/cap `customer_statement`; add a scheduled denormalized-field reconciliation command; automate DB/media backups.

---

## 5. Answers to the Review Questions

1. **Remaining issues:** see §3 — 5 High, 9 Medium, 6 Low. No new *critical* holes; the previously critical items (RBAC, refund/overpayment, returns ledger) are fixed.
2. **Production-ready?** No — not yet. Core money-handling is now correct, but the High items (credit limit, partial report netting, RBAC lockout, password validation, committed `.env.cpanel`) must be resolved first.
3. **Safe to deploy now?** No. Deploying as-is risks: approved staff locked out (RBAC role gap), unbounded credit sales, exposed cPanel secret, and total outage if `createcachetable` is skipped. Fix P0 + P1 first.
4. **Final recommendations:** complete P0/P1, then run `python manage.py check --deploy`, the full test suite (add RBAC tests), and a staging smoke test on the target cPanel host (verify Passenger boot, cache table, media, SSL redirect) before go-live.

---

## Open Business Questions (unchanged, block some fixes)
1. Credit-limit policy: hard block vs. warn-and-allow, and who can override?
2. Overpayment/advances: model store credit, or strictly cap at due?
3. Refund approval: separate approver role required?
4. Suppliers: first-class ledger, or free-text acceptable?
