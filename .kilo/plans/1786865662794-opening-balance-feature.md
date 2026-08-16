# Customer Opening Balance Plan

## Goal

Allow authorized staff to record a customer's pre-system outstanding debt without creating a fake sale. The amount must affect customer outstanding dues and statements, while leaving sales, stock, purchase totals, and profit reports unchanged.

## Decisions

1. Store the opening debt on `Customer`, with an explicit effective date. Do not infer the date from `created_at`.
2. Opening balance is debt only: the amount must be zero or greater. Pre-system customer credits are out of scope.
3. Keep `total_purchases` and `total_paid` as system transaction totals. Add the opening balance only to `total_due`.
4. Use a dedicated `customers.set_opening_balance` permission. Manager and Admin receive it; Cashier does not. Do not reuse `change_customer`, because the current Cashier group receives that permission.
5. Opening-balance edits are allowed after initial entry and each successful change is audit logged.
6. The opening balance is represented as a synthetic statement entry, never as `Sale`, `Payment`, or `SaleReturn` data.

## Existing Behavior To Preserve

- `Customer.recalculate_balance()` aggregates completed sales, payments, and sale refunds.
- Sale totals already exclude returned goods; refund cash is separately netted from customer payments.
- Payment validation limits general customer payments against `customer.total_due`.
- Sales, stock, and profit reports query sales/sale items directly and must remain unaffected.
- Walk-in payments have no customer and must continue to work unchanged.
- Existing date-range statement behavior carries transactions before `date_from` into a brought-forward balance.

## Implementation

### 1. Model and migration

Modify `apps/customers/models.py`:

- Add `opening_balance` as a non-negative `DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))`.
- Add `opening_balance_date` as a `DateField(default=timezone.localdate)` so existing customers receive a deterministic migration value and new entries default to today.
- Add a custom permission in `Customer.Meta`: `set_opening_balance`, for example, `Can set customer opening balance`.
- Update `recalculate_balance()` to set:
  `total_due = opening_balance + sales_total - (payments_total - refunds_total)`.
- Keep `total_purchases = sales_total` and `total_paid = payments_total - refunds_total` unchanged.

Create the next customers migration after `0007` with defaults that preserve all existing balances (`0.00` and the migration date/current local date as appropriate), then run Django migration checks.

### 2. Form and permissioned view

Modify `apps/customers/forms.py`:

- Add `OpeningBalanceForm` for `opening_balance` and `opening_balance_date` only.
- Validate the amount as non-negative and the date as required.
- Use the existing form styling conventions.

Modify `apps/customers/views.py`:

- Add `opening_balance_set(request, pk)` protected by `@has_permission('customers.set_opening_balance')`.
- On GET, show the current values.
- On valid POST, save both fields atomically, call `recalculate_balance()`, and write an audit log containing old/new amount and old/new effective date. Redirect to customer detail with a success message.
- Do not expose opening-balance fields through `CustomerForm`, customer creation, or the inline customer-create API, preventing Cashiers from setting debt during normal customer creation.
- Include `opening_balance` and `opening_balance_date` in `api_customer_info`.

Add the route in `apps/customers/urls.py`:
`<int:pk>/opening-balance/` named `opening_balance_set`.

### 3. Role setup and admin

Modify `apps/core/management/commands/setup_groups.py`:

- Explicitly include the new permission for Manager and Admin groups.
- Explicitly exclude it from Cashier permissions, even though Cashier currently receives most non-delete customer permissions.
- Keep the command idempotent.

Modify `apps/customers/admin.py`:

- Display the opening amount/date in the customer admin.
- Make the fields editable only for users with `customers.set_opening_balance`; otherwise mark them read-only or remove them from editable fieldsets. This prevents Django admin from bypassing the dedicated permission.
- Preserve existing read-only denormalized totals.

### 4. Customer UI

Modify `templates/customers/customer_detail.html`:

- Show the opening balance and effective date near the financial summary.
- Show an edit/set action only when the current user has `customers.set_opening_balance`.
- Keep outstanding due based on `customer.total_due`.

Add `templates/customers/opening_balance_form.html` using the existing page/form layout and CSRF/error handling.

### 5. Statement behavior

Modify `customer_statement()` and its template:

- Add the persistent opening-balance entry with `opening_balance_date`, type `Opening Balance`, and debit equal to the amount.
- Include completed `SaleReturn` rows for the customer's sales. Since sale invoice totals are already reduced by returned goods, represent the cash refund as a debit equal to `refund_amount`; this keeps the statement arithmetic consistent with `recalculate_balance()`.
- For an unfiltered statement, sort opening balance, invoices, payments, and returns chronologically and calculate the running balance from zero.
- For a `date_from` filter, calculate brought-forward balance from the opening balance when its effective date is before the window, plus all prior sales, payments, and returns. Display that brought-forward amount separately; do not duplicate the persistent opening row inside the filtered transaction list.
- Include the persistent opening row in the filtered transaction list when its effective date falls inside the requested date window. Respect `date_to` for all transaction types.
- Keep current balance in the footer as the customer's full current `total_due`; retain the filtered closing/running balance separately if the existing template exposes it.
- Use consistent date-only values for sorting and rendering, and define same-day ordering deterministically (opening balance before sales, returns before/after payments according to the existing ledger convention; cover it in tests).

### 6. Tests

Add focused tests under `apps/customers/tests`:

- Model balance with zero opening balance remains unchanged.
- Opening balance alone sets `total_due` without changing `total_purchases` or `total_paid`.
- Sale plus opening balance computes the expected due.
- Payment reduces due, and refunds preserve the existing return-aware formula.
- Opening-balance form accepts zero/positive values and rejects negative/invalid values and missing dates.
- View permission: Manager/Admin can GET and POST; Cashier is redirected/denied; invalid POST does not change data; successful changes recalculate balance and create an audit record.
- Migration/default behavior for existing customers.
- API contains opening amount/date.
- Statement includes the opening row, carries it forward correctly for date ranges, includes payments and returns, and does not duplicate the opening row.
- Existing reports do not count the opening balance as sales or profit.
- Existing walk-in payment behavior remains covered.

## Validation

1. Run `python manage.py makemigrations --check` and the customers/sales test suites.
2. Run the complete Django test suite if the focused tests pass.
3. Run `python manage.py check`.
4. Smoke test Manager, Admin, and Cashier access, then verify customer detail, statement filters, API output, payment entry, returns, and sales/profit reports.

## Risks

- Denormalized `total_due` can be stale for old records; the migration should not rewrite unrelated totals, and the opening-balance save must always call `recalculate_balance()`.
- Statement arithmetic can diverge if returns are omitted or represented as returned goods and refunds simultaneously; use the existing net sale totals plus refund debit rule above.
- Admin field permissions can accidentally bypass the dedicated route; enforce them in `CustomerAdmin` as well as the view.
- Existing customers must receive zero opening debt and a valid effective date during migration.
