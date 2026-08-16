# Sale Create Responsive and Transfer Fixes

## Goal

Make `sales/create/` reliable and comfortable on phone-sized screens while making quick stock transfer permissions, availability, quantities, and concurrency consistent with checkout business rules.

## Decisions

- Quick transfer from Sale Create is for fulfilling the current cart shortage only. The combined transfer quantity must not exceed `max(0, required_quantity - shop_stock)`.
- `total_stock` remains informational. Transfer decisions use active, non-shop warehouse stock only.
- No new stock denormalization fields are required. Return calculated `transferable_stock` from the API and derive it from `ProductStock` rows.
- Checkout remains the authoritative final validation. Client-side limits are usability safeguards, not security controls.
- Existing standalone warehouse transfer workflow remains available; quick transfer uses the dedicated stock-transfer permission and must not silently broaden cashier privileges.

## Findings To Address

1. Transfer controls are rendered to sale users who may lack `warehouse.add_stocktransfer`; unauthorized API responses are HTML redirects while JavaScript expects JSON.
2. Product search uses `Product.total_stock`, and warehouse-stock lookup includes inactive warehouses, so “stock available” can be non-transferable.
3. Cart quantity can grow without a shop plus transferable-stock cap.
4. Quick-transfer APIs have no focused sales tests, including permission, rollback, stale stock, and concurrency behavior.
5. The transfer modal allows more than the current shortage and its `Max` action can drain a warehouse.
6. The cart remains a horizontally scrolling table on mobile and transfer rows are too wide for narrow phones.
7. Mobile controls have undersized touch targets, search results are dense, and the sticky checkout action is not a true mobile action bar.
8. Fresh transfer stock is only partially written into cart state; `line.totalStock = line.totalStock` is a no-op.
9. Checkout can accept inactive products through a crafted or stale payload.

## Implementation Plan

### 1. Establish transfer permission behavior

- Inspect and normalize the actual warehouse permission codenames used by `Warehouse`/`StockTransfer`, `setup_groups.py`, and the two quick-transfer decorators. Do not assume `add_transfer` and `add_stocktransfer` are interchangeable.
- Ensure the intended role policy is explicit: users who can create sales but cannot transfer stock must not see the transfer action or be allowed to use the quick-transfer APIs. Preserve Manager/Admin access according to the existing warehouse policy and keep Cashier access deliberate.
- Update `sale_create()` context and `sale_form.html` with a `can_quick_transfer` flag, or equivalent `perms` check. Hide transfer buttons and warehouse-only cart affordances when false.
- Add an AJAX-aware permission response for the quick-transfer endpoints, preferably JSON 403 for `X-Requested-With`/JSON requests, while preserving normal unauthorized redirects elsewhere.

### 2. Correct stock availability APIs

- Update `api_product_search()` to calculate or return `transferable_stock` as the sum of positive `ProductStock.quantity` in active, non-shop warehouses.
- Keep `shop_stock` scoped to the active shop warehouse and keep `total_stock` as the product’s overall informational aggregate.
- Update `api_product_warehouse_stocks()` to filter active, non-shop warehouses and return `shop_stock`, `transferable_stock`, and `total_stock` consistently.
- Make the product search UI use `transferable_stock` for “warehouse stock available,” adding depot-only products only when there is actually transferable active stock and the user has transfer permission.
- Return a fresh stock payload from quick transfer, including new shop, transferable, and total values.

### 3. Enforce shortage-only transfer logic server-side

- In `api_quick_transfer()`, validate the product is active, the destination is the current active shop, every source is active and non-shop, and all entries are unique and positive.
- Determine the current cart shortage from a client-supplied required quantity, or add the required quantity to the request payload. Validate that the requested combined transfer is no greater than the current shortage. Do not trust the client’s displayed shop stock; recompute current shop stock under the transaction.
- Lock all affected source and destination `ProductStock` rows in deterministic product/warehouse order before validation and mutation, or otherwise make the multi-source operation lock-safe. Preserve atomic rollback if any source is insufficient.
- Keep transfer records and audit logs for each source warehouse, but ensure the operation cannot partially commit.
- Update the JavaScript payload to send `required_quantity` and handle server rejection as a clear stale-stock message that refreshes the modal data.

### 4. Bound cart quantities and keep state fresh

- Store `transferableStock` and an effective `availableOverall` value on every cart line.
- Cap plus buttons and typed quantities at `shop_stock + transferable_stock` when transfer is allowed. If transfer is unavailable, cap at shop stock.
- Show a concise availability message when the cap is reached, distinguishing “in shop” from “available in warehouses.”
- After warehouse-stock lookup, update `line.stock`, `line.transferableStock`, and `line.totalStock` from the server response.
- After successful transfer, update all stock values from the response and retain the same line quantity; render the line as valid when shop stock now covers it.
- Clear transfer state and restore button text correctly after success, API validation failure, network failure, and modal close.

### 5. Improve the mobile cart and checkout workflow

- Preserve the desktop table at larger breakpoints, but add a mobile presentation below the project’s tablet breakpoint, preferably stacked line blocks rather than relying on horizontal scrolling.
- On mobile, group each line as product/stock, price/quantity controls, shortage/transfer action, line total, and remove action. Keep product identity and line total immediately visible.
- Make quantity, remove, customer-clear, transfer, and modal controls at least approximately 40 to 44px touch targets without making the visual design bulky.
- Replace the current mobile sticky action behavior with a clear bottom action bar containing the grand total and Complete Sale. Respect `env(safe-area-inset-bottom)` and add page bottom padding so content is not obscured.
- Make the transfer modal `modal-fullscreen-sm-down` or equivalent on small screens. Reflow warehouse rows into a two-line/grid layout with a full-width quantity input and a shortage-focused action.
- Replace “Max” with “Fill shortage,” set each row’s maximum to the remaining shortage, and disable inputs once the combined shortage is satisfied.
- Reduce mobile result density: put price/stock on a second line, use concise `Shop / Warehouse / Total` labels, and avoid crowding average cost into the product title.
- Use a viewport-aware result list such as `max-height: min(22rem, 45dvh)` and contain overscroll when the mobile keyboard is open.

### 6. Tighten checkout validation

- Change `SaleService.create_from_pos()` to fetch only active products and reject inactive product IDs explicitly.
- Confirm the service locks the active shop stock rows and rejects stale quantities with a clear message. Keep all price, discount, payment, credit, customer, and stock validation server-side.
- Consider rejecting inactive customer IDs if the project’s customer policy disallows sales to inactive accounts; document the chosen behavior in tests rather than changing it implicitly.
- Ensure the UI handles JSON 400/403/409 responses without treating them as network failures.

## Tests

Add or extend focused tests under `apps/sales/tests` and relevant warehouse tests:

- Product search returns correct `shop_stock`, `transferable_stock`, and `total_stock` with inactive warehouses excluded.
- Product search and warehouse-stock APIs handle no shop, inactive products, unauthorized users, and JSON authorization errors.
- Cashier/Manager/Admin quick-transfer access matches the finalized permission policy.
- Quick transfer rejects inactive sources, shop-as-source, duplicate sources, malformed quantities, zero quantities, and transfers over the current shortage.
- Successful multi-source transfer moves the exact shortage, creates expected transfer/audit records, updates source/destination stock, and leaves total stock unchanged.
- Any insufficient source causes complete rollback with no transfer records or stock drift.
- Concurrent or stale transfer attempts cannot overdraw source stock.
- Cart/UI behavior is covered with JavaScript tests if the project has a browser test harness; otherwise add server/API regression tests and manually verify the responsive states.
- Checkout rejects inactive products and preserves existing walk-in, payment, credit-limit, discount, and shop-stock behavior.
- Add template smoke assertions for transfer affordance visibility and required data attributes.

## Validation

1. Run `python manage.py makemigrations --check --dry-run` and `python manage.py check`.
2. Run focused sales, warehouse, inventory, and permission tests.
3. Run the full Django suite in a supported Python/Django environment. The current Python 3.14 plus Django 4.2 test-rendering incompatibility must not be treated as a passing full-suite result.
4. Use browser/device checks at approximately 320px, 375px, 768px, and desktop widths.
5. Smoke test: shop stock available, warehouse-only stock, no stock, unauthorized transfer user, stale stock after another transfer, multi-warehouse shortage, successful checkout after transfer, and network/API failure states.

## Risks

- Changing permission assignment can affect existing Cashier workflows; run the group setup command in a test database and assert exact permissions.
- `Product.total_stock` may already be stale in legacy data. The APIs should expose the distinction without silently rewriting unrelated inventory records.
- Locking multiple stock rows must use a deterministic order to avoid deadlocks.
- Mobile layout changes must retain keyboard scanning and desktop barcode workflows.
