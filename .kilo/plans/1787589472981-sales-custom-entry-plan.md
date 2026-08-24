# Sales Custom Entry Plan

## Context and Decisions

- The Sales `SaleItem` model already supports custom entries with nullable `product`, nullable `warehouse`, `is_custom`, and `custom_description`; no migration is required.
- The current Sales UI has product search and cart controls but no custom-item affordance or modal.
- `SaleService.create_from_pos()` currently rejects every item without `product_id`, then resolves stock and cost for every line.
- Custom sale lines will follow the existing Quotation custom-entry contract:
  - Required description, maximum 255 characters.
  - Unit price defaults to zero and must be non-negative.
  - Quantity defaults to one and must be at least one.
  - Payload uses `product_id: null`, `is_custom: true`, and `custom_description`.
- Custom lines have no inventory impact, no warehouse, and zero cost price. Product-backed lines retain all current product, stock, transfer, discount, payment, and validation behavior.
- The request is limited to adding custom entries on the Sales page. Do not change quotation behavior, navigation, customer behavior, stock-transfer behavior, sale detail/print behavior, or unrelated templates.

## Implementation Tasks

1. Update `templates/sales/sale_form.html`:
   - Change the product-search help text to offer `add a custom item`, while retaining the existing search instructions.
   - Add a Sales custom-item Bootstrap modal using the same established modal structure and controls as Quotations.
   - Use Sales-specific IDs such as `saleCustomItemModal`, `saleCustomDesc`, `saleCustomPrice`, `saleCustomQty`, and `btnSaleCustomAdd` to avoid collisions and preserve existing IDs.
   - Keep the existing sale form, payment modal, customer modal, and transfer modal unchanged.
   - Increment only the `sale-create.js` cache-busting version.

2. Update `static/js/sale-create.js`:
   - Add cached references for the custom-item modal controls.
   - Add a `nextCustomId` counter and represent custom lines distinctly from product lines, for example with `isCustom`, `productId: null`, `label/customDescription`, `unitPrice`, `qty`, `discount: 0`, and zero stock/transfer values.
   - Add an “add custom item” click handler that resets description, price, and quantity and opens the modal.
   - Validate a non-empty description, non-negative price, and quantity of at least one using the same normalization style as the existing quotation flow.
   - Add custom lines to the cart, render their description safely, and bypass product SKU/stock/warehouse-transfer presentation for custom rows.
   - Ensure custom rows retain editable price and quantity controls and can be removed like product rows.
   - Keep stock limits and transfer controls active only for product-backed rows.
   - Include `is_custom`, `custom_description`, and `product_id: null` in the checkout payload for custom lines; retain the current payload for product lines.
   - Keep existing subtotal, order discount, payment, confirmation, reset, success, customer, and transfer flows unchanged.
   - Ensure custom descriptions are HTML-escaped through the existing rendering helper.

3. Update `apps/sales/services.py`:
   - Extend payload parsing to recognize `is_custom`.
   - For custom items, require a non-empty `custom_description` of at most 255 characters, require/normalize quantity and unit price using the existing numeric validation rules, and do not require or parse a product ID.
   - For product items, preserve all current requirements and errors: product ID required, valid active product, positive quantity, non-negative price/discount, and line discount not exceeding the line total.
   - Keep custom item discounts at zero or validate them with the same existing line-discount rules if supplied; do not introduce a new UI for custom discounts.
   - Exclude custom items from product lookup, shop-stock row locking, stock decrement, and product total-stock refresh.
   - Create custom `SaleItem` rows with `product=None`, `warehouse=None`, `cost_price=Decimal('0.00')`, `is_custom=True`, and the submitted description, quantity, price, and discount.
   - Include custom line totals in subtotal and total calculations, while leaving product cost calculation unchanged.
   - Preserve the current atomic rollback behavior for invalid mixed carts, including a custom line followed by an invalid product line.

4. Add focused tests in `apps/sales/tests/test_views.py`:
   - A custom-only sale succeeds with the expected `SaleItem` fields, subtotal, total, zero cost, and no stock changes.
   - A mixed product/custom sale succeeds, deducts stock only for the product line, and includes both line totals in the sale subtotal.
   - Custom descriptions are required and length-limited; malformed/negative custom prices and invalid quantities return the existing JSON error shape and create no records.
   - A custom item does not require product stock, warehouse stock, or product search permission beyond the existing checkout permission.
   - A custom line does not trigger warehouse transfer behavior or stock mutation.
   - Invalid product data in a mixed cart rolls back any custom/product writes and stock changes.
   - Existing product-only checkout tests continue to pass unchanged.
   - The Sales page renders the custom-item button and modal controls.

## Data and Failure Handling

- The entire checkout remains under the existing `transaction.atomic` service boundary.
- Custom lines must never decrement or inspect inventory stock and must never receive a product or warehouse reference.
- Product lines must continue to enforce stock availability exactly as before.
- Empty custom descriptions are rejected server-side even if client-side validation is bypassed.
- Overlong descriptions are rejected before any sale or stock write.
- A failed mixed cart must leave no `Sale`, `SaleItem`, `Payment`, or stock mutation.
- No model or migration changes are expected.

## Validation Checklist

- Run `python manage.py test apps.sales.tests`.
- Run `python manage.py check`.
- Verify custom-only and mixed carts through the JSON checkout path.
- Verify normal product checkout, stock transfer affordances, customer/payment handling, and success modal behavior remain unchanged.
- Run `git diff --check` before delivery.
