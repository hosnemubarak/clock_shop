# Sale Return Implementation — Finalized Plan

Implement full/partial sale returns for every invoice (walk-in + registered customers). `SaleReturn`/`SaleReturnItem` already exist as shells (apps/sales/models.py:201-246) — this plan wires them in. **All schema changes are additive with defaults; no existing data or behavior changes until a return is created.**

## Code-Review Findings — Corrections to the Draft Plan

The draft plan had 4 contradictions with existing code. These are corrected below:

1. **DO NOT adjust `paid_amount` on over-paid returns.** `Sale.paid_amount` must equal `Σ Payment.amount` — enforced by `Sale.recalculate_paid_amount()` (apps/sales/models.py:120) and the `fix_sale_payments` management command, which would revert any manual adjustment and corrupt figures. Instead: leave `paid_amount` untouched; after return the `due_amount = total_amount - paid_amount` may go **negative = store credit**. `payment_status` stays correct via existing `update_payment_status()` (`paid >= total → paid`). The over-payment test asserts `paid_amount` unchanged + negative due.
2. **`sales_report` must NOT subtract returns from `total_amount` aggregates.** Sale totals are mutated downward by returns (already net) — subtracting again double-counts. Only the **SaleItem-based** aggregations (`top_products`, and all of `profit_report`, dashboard `profit_month`) need return subtraction, because `SaleItem.quantity` is never mutated.
3. **Customer statement must debit the ORIGINAL invoice amount.** Statement reads `sale.total_amount` (post-return net). Adding return credits on top double-counts. Fix: debit = `sale.total_amount + sale.total_returned_amount`.
4. **`sale_cancel` must block sales that have returns.** Otherwise cancel restores full original quantities to batches → double stock restore (returns already restored part).

## Exact Financial Algorithm (canonical, in `process_return()`)

Per return, using **proportion-of-remaining** (self-consistent across multiple partial returns):

- `line_gross = Σ(ri.quantity × ri.unit_price_snapshot)` (snapshot from `SaleItem.unit_price` at return time)
- `item_discount_share = Σ(sale_item.discount × ri.quantity / sale_item.quantity)` (proportional per-unit)
- `remaining_gross_before = Σ over items of (quantity − already_returned) × unit_price` (guard ÷0 → shares are 0)
- `invoice_discount_share = sale.discount_amount × line_gross / remaining_gross_before` (discount_amount is already net of prior returns — proportion of remaining is exactly right)
- `tax_share = sale.tax_amount × line_gross / remaining_gross_before`
- **`refund_amount = line_gross − item_discount_share − invoice_discount_share + tax_share`**, each share quantized `Decimal('0.01')` ROUND_HALF_UP
- **Full-return snap:** if every sale item reaches `returned_quantity == quantity`, set `subtotal = discount_amount = tax_amount = total_amount = total_cost = 0` and `refund_amount = total_amount_before_this_return` (guarantees `Σ refunds == original total`, no rounding dust). Otherwise cap `refund_amount` at current `total_amount`.

Sale updates per return: `subtotal −= line_gross − item_discount_share`; `total_cost −= Σ(ri.quantity × ri.cost_price_snapshot)`; `discount_amount −= invoice_discount_share`; `tax_amount −= tax_share`; `total_amount = subtotal − discount_amount + tax_amount`; call `update_payment_status()`.

Worked example (verified): subtotal 1090 (A: 10×100, B: 2×50 −10 disc), invoice disc 100, tax 50, total 1040. Return 5×A → refund 477.28, sale total 562.72. Then return rest → refund 562.72, total 0. Σ refunds = 1040 ✓.

## Tasks

### 1. [MODIFY] apps/sales/models.py

- **`SaleReturn`**: add `status` (`completed`/`cancelled`, default `'completed'` — cancellation flow itself is OUT OF SCOPE this iteration), `notes` (blank TextField). Add `process_return()`:
  1. `transaction.atomic()` + `Sale.objects.select_for_update().get(pk=...)` re-fetch; re-validate every `ri.quantity ≤ returnable_quantity` inside the lock (race/duplicate protection — mirrors `StockOut.complete_stockout` pattern, apps/inventory/models.py:269)
  2. Restore stock per return item (skip `is_custom`/no-batch items): `batch.quantity += ri.quantity; batch.save(); product.update_total_stock()`
  3. Compute refund per algorithm above; set `self.refund_amount`; save
  4. `sale.recalculate_after_return()` (new method applying the sale field updates above)
  5. Registered customer: `sale.customer.recalculate_balance()` (REUSES existing logic apps/customers/models.py:77 — recomputes from mutated sale totals + untouched payments; walk-in `customer is None` skips)
  6. `sale.update_payment_status()`
- **`SaleReturnItem`**: add `unit_price`, `cost_price` decimal fields (default `0.00`, snapshot at creation); fix `__str__` crash for custom items (`product` is None → use `sale_item.custom_description`); add `related_name='return_items'` on `sale_item` FK (safe `AlterField`, no data change). Add `line_total` property = `quantity × unit_price`.
- **`SaleItem`**: add `returned_quantity` property (`return_items.aggregate`, filter `sale_return__status='completed'`) and `returnable_quantity` = `quantity − returned_quantity`.
- **`Sale`**: add `total_returned_amount` (Σ completed `returns.refund_amount`), `has_returns` properties; add `recalculate_after_return()` per algorithm.

### 2. [MODIFY] apps/core/models.py

Add `('SALE_RETURN', 'Sale Return')` to `AuditLog.ACTION_CHOICES` (code-only; CharField choices are not DB-enforced — no migration impact on existing rows).

### 3. [NEW] apps/sales/migrations/0003_*.py (auto-generated via makemigrations)

Additive only: `SaleReturn.status` (default `completed`), `SaleReturn.notes`, `SaleReturnItem.unit_price`/`cost_price` (default 0), AlterField `sale_item` related_name. Existing production rows get valid defaults. **Run `python manage.py makemigrations sales` and review the generated file before applying; `python manage.py migrate` on a DB BACKUP copy first.**

### 4. [MODIFY] apps/sales/views.py

- **`sale_return_create(request, pk)`** (new): GET renders form (items + returnable qty via ONE aggregated query `{sale_item_id: returned_qty}` to avoid N+1). POST: require `sale.status == 'completed'`; parse `return_qty_<item_id>` + `reason`; validate 1 ≤ qty ≤ returnable, ≥1 item selected; inside `transaction.atomic()` create `SaleReturn` + items with price snapshots, call `process_return()`, `create_audit_log(request, 'SALE_RETURN', sale_return, {...})`. Identical flow for walk-in (no customer branch needed — model handles it).
- **`sale_return_detail(request, pk)`** (new): return header + items + refund summary.
- **`sale_detail`**: prefetch `returns__items__sale_item`; pass returnable-qty dict.
- **`sale_cancel`**: add guard — if `sale.has_returns`, error "Cannot cancel a sale with returns" (prevents double stock restore).

### 5. [MODIFY] apps/sales/urls.py

Add: `path('<int:pk>/return/', views.sale_return_create, name='sale_return_create')` and `path('returns/<int:pk>/', views.sale_return_detail, name='sale_return_detail')`. (No conflict: `returns/` is non-numeric so `<int:pk>/` never captures it.)

### 6. Templates (extend base.html; reuse card/table patterns, `CURRENCY_SYMBOL`, `showConfirmModal`/`showValidationModal`)

- **[NEW] templates/sales/sale_return_form.html**: invoice summary header; per-item rows (product/batch, sold qty, already returned, max returnable, qty input `min=1 max=returnable`, unit price readonly; custom items included with "no stock effect" note); reason textarea (required); live JS refund summary implementing the same proportional formula (pass `discount_amount`, `tax_amount`, `remaining_gross` as data attributes); `showConfirmModal` before submit.
- **[MODIFY] templates/sales/sale_detail.html**: "Return Items" button (visible when `status == 'completed'` and any `returnable_quantity > 0`); "Returned" column in items table (`returned/quantity`, e.g. "3 / 10"); "Return History" card (return number, date, items count, refund, link to detail); show negative due as "Credit" badge instead of "Due".
- **[NEW] templates/sales/sale_return_detail.html**: return header (number, linked invoice, date, reason, created by), items table (qty × price = line total), refund summary.

### 7. [MODIFY] apps/sales/admin.py

Add `status`, `notes` to `SaleReturnAdmin` list_display/fieldsets; `unit_price`, `cost_price` to `SaleReturnItemInline` readonly fields.

### 8. Reports — return-aware WITHOUT double-counting

- **apps/reports/views.py `sales_report`**: summary/period totals stay as-is (already net via mutated `total_amount`); add informational "Returns in period" stat = `Σ SaleReturn.refund_amount` (`status='completed'`, `return_date` in range); fix `top_products`: subtract per-product returned qty/revenue (`SaleReturnItem` joined via `sale_item`, sales in date range) — merge in Python.
- **`profit_report`**: subtract per-product returned `quantity`, `quantity×unit_price`, `quantity×cost_price` from `profit_by_product`, `profit_by_category`, `profit_by_warehouse`, and `totals` (same SaleItem→SaleReturnItem join, sales in range; custom items excluded as today).
- **`customer_report`**: no math change (balances already correct via `recalculate_balance`); add total-returns stat (Σ refund amounts).
- **apps/core/views.py dashboard**: `profit_month` (SaleItem-based, line 35) subtract returned `(unit_price − cost_price) × qty` for the month; `total_sales_*` need no change (mutated totals).

### 9. [MODIFY] apps/customers/views.py `customer_statement`

Add `SaleReturn` rows (`sale__customer=customer`, `status='completed'`, date-filtered on `return_date`) as credit transactions (type "Return", reference `return_number`, credit = `refund_amount`); change invoice debit to `sale.total_amount + sale.total_returned_amount` (original invoice amount) so the ledger balances exactly.

### 10. [NEW] apps/sales/tests.py (no tests exist anywhere today — first suite)

Django test runner uses an isolated test DB; production data untouched. Cover:

| Test | Asserts |
|---|---|
| `test_full_return_registered_customer` | stock restored (batch + `total_stock`), sale totals all zero, `Σ refunds == original total`, customer `total_purchases/total_due` reduced via recalc |
| `test_partial_return_single_item` | totals per algorithm, remaining qty correct |
| `test_partial_return_multiple_items` | multi-line refund math |
| `test_multiple_sequential_returns` | two returns; cumulative = full-return snap; cannot exceed remaining |
| `test_return_exceeds_quantity_rejected` | validation error |
| `test_return_exceeds_remaining_rejected` | after partial return, over-return rejected |
| `test_walk_in_return` | no customer; stock restored; no customer errors |
| `test_return_stock_restoration` | batch.quantity and product.total_stock exact |
| `test_return_refund_calculation` | worked example above (refund 477.28 / 562.72) |
| `test_cancelled_sale_no_return` | view/model rejects |
| `test_return_custom_item` | financials only, no stock ops, no crash in `__str__` |
| `test_overpaid_sale_return` | `paid_amount` UNCHANGED, due negative (credit), `payment_status='paid'` |
| `test_invoice_discount_tax_proration` | proportional shares incl. rounding quantize |
| `test_return_race_duplicate_protection` | second return beyond remaining rejected inside atomic revalidation |
| `test_cancel_sale_with_returns_blocked` | sale_cancel guard |

## Decisions & Rationale

- **Store credit model for over-paid returns** (vs mutating `paid_amount`): preserves the `paid_amount == Σ Payment` invariant; no changes to `Payment` model/validator (which forbids negative amounts). Cash refunds to walk-ins are recorded by the `SaleReturn.refund_amount` itself.
- **Mutate sale totals, preserve sale items**: original invoice is fully reconstructible (`original_total = total_amount + total_returned_amount`); due/payment/customer/report logic all read mutated totals — maximal reuse, zero duplication.
- **`recalculate_balance()` reuse** (not incremental +=/−=): derives from source of truth, immune to drift.
- **"Charges"**: `Sale` has no charges/shipping field (only discount + tax) — nothing to do; noted for completeness.
- **Return cancellation flow**: OUT OF SCOPE (status field present and all aggregations filter `status='completed'` so it can be added later safely).

## Risks & Mitigations

- **Migration on production DB**: additive-only, defaults provided; test on backup first; `makemigrations --check` in CI habit.
- **Concurrent returns on same invoice**: `select_for_update` + in-lock revalidation (SQLite ignores `select_for_update` silently — same as existing `StockOut` code; its transaction-level locking makes this safe).
- **Rounding drift on repeated partial returns**: quantize every share; full-return snap guarantees exact zero/exact total refund.
- **Historical report shifts**: a later return retroactively reduces an older period's sale totals (inherent to net-totals design, consistent with how the whole app reads `total_amount`); the "Returns in period" stat gives visibility.

## Verification

1. `python manage.py makemigrations --check --dry-run` (no unexpected diffs)
2. `python manage.py test apps.sales -v2` (new suite green)
3. `python manage.py test apps.customers apps.reports -v2` (no regressions)
4. Manual on dev copy of production DB: partial payment + partial return → check all figures; walk-in full return → stock exact, no customer ops; over-return rejected; two sequential partial returns → cumulative correct; customer statement balances (Σdebits − Σcredits == final `total_due`)
