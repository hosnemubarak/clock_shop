# Sales Create — Fix & Polish Plan

Plan ID: 1785750974656
Scope: **Sales Create page only** (`sales/create/`). No other templates change.
Goal: Make the sale screen reliable (no "works only after refresh" bugs), simpler, and consistent with the Return page's clean card style — without regressing its already-strong JS architecture.

---

## Context & Findings (verified against code)

- `templates/sales/sale_form.html` — page markup; loads `css/sale-create.css` and `js/sale-create.js?v=7`. Posts nothing; JS sends JSON to `sales:pos_checkout`.
- `static/js/sale-create.js` (947 lines) — one IIFE, no globals. Product search is a **bespoke, reliable dropdown**: debounced (180ms), `AbortController`, keyboard nav, barcode auto-add, integer-paisa money math, delegated listeners, ARIA. This is the good pattern to reuse.
- The **customer field uses TomSelect**, which is the source of every reliability symptom:
  - `sale-create.js:17-21` force-reloads the whole page on BFCache restore ("TomSelect and cart state break or become stale") — a band-aid.
  - `static/css/sale-create.css:323-338` — `z-index: 9999 !important` / `10000 !important` "war" hack to force the dropdown clickable over the theme.
  - `sale-create.js:907-922` — TomSelect `load()` has **no debounce and no abort**; `shouldLoad: return true` fires an un-cancelled `/customers/api/search/` on every keystroke.
- Theme JS does **not** touch selects/TomSelect: `static/js/app.js` only lazy-loads `choices.js` for `[data-choices]` (none on this page). So the customer bug is the page's own TomSelect lifecycle, not a theme fight. Removing TomSelect here resolves it.
- Backend contracts to preserve unchanged:
  - `sales:pos_checkout` JSON payload (`sale-create.js:440-455`): `items[].{product_id,quantity,unit_price,discount}`, `customer_id`, `sale_date`, `notes`, `discount_amount`, `payment_method`, `payment_amount`.
  - `customers:api_customer_search` returns `{results:[{id,name,phone}]}`.
  - `customers:api_customer_info` (`/customers/api/<id>/`) returns `{name,phone,total_due,loyalty?}`.
  - `customers:api_customer_create` returns `{status,customer:{id,name,phone}}`.
  - `sales:api_product_search` returns `{results:[{id,sku,brand,category,display_name,price,shop_stock,total_stock}], truncated}`.
- The `SaleForm` renders `<select name="customer" class="form-select">` with an empty queryset (options fetched via AJAX). The **hidden `<select name="customer">` must stay** so `customer_id` still posts.

## Decisions (resolved)

1. Scope: Sales Create only. **No site-wide redesign.**
2. Customer selector: **replace TomSelect** with the page's own search-dropdown pattern (a "customer search" mirroring product search) + a selected-customer "chip" with a Clear button. Keep a hidden `<select name="customer">` (or `<input type="hidden" name="customer">`) so the POST contract is unchanged.
3. Investigate/fix **all** lifecycle bugs; remove both band-aids (BFCache reload, z-index hack) once TomSelect is gone.
4. Category/Brand filter dropdowns: **deferred** (search already matches brand/category by name). No backend change.
5. Visual polish: reuse existing components (`includes/page_header.html` already used; Bootstrap cards). Keep changes CSS-light and consistent with Return page.
6. Keep the strong existing JS patterns (debounce, AbortController, paisa math, delegated listeners, keyboard shortcuts). Do **not** copy Return's simpler inline-script pattern.

---

## Implementation Tasks (ordered)

### Phase 1 — Replace customer TomSelect (removes the biggest bug cluster)

1. **Markup (`sale_form.html`)** — Replace the `{{ form.customer }}` TomSelect select block (lines ~54-68) with a customer search control mirroring the product search:
   - A hidden field `<input type="hidden" name="customer" id="customerId">` (or keep the `<select>` hidden) to carry `customer_id`.
   - A text input `#customerSearch` (search combobox, ARIA like `#productSearch`) with placeholder "Search customer by name or phone…".
   - A results `<ul id="customerResults" role="listbox" hidden>`.
   - Keep the existing "New" customer button (`data-sale-action="new-customer"`).
   - Keep the existing `#customerMetaBox` info card (name / phone / outstanding due / loyalty) — it already renders from `loadCustomerMeta()`.
   - Default state = Walk-in (empty customer id), with a visible "Walk-in customer" chip and a way to search/select a real customer; selecting one shows a chip with a Clear (×) button that returns to Walk-in.

2. **JS (`sale-create.js`)** — Generalize the product-search dropdown into a small reusable in-file factory OR add a parallel `customerSearch` block that reuses the same helpers (`escapeHtml`, `highlight`, debounce, `AbortController`, keyboard nav). Requirements:
   - Debounced (reuse `SEARCH_DEBOUNCE_MS`) fetch to `CFG.customerSearchUrl`; abort in-flight request on new keystroke.
   - Arrow-up/down + Enter to select; Escape closes; click/mousedown selects; outside-click closes.
   - On select: set hidden `customer` value, render the chip, call `loadCustomerMeta(id)`.
   - On clear: reset to Walk-in (empty value), hide meta box.
   - Delete the `TomSelect` init block (`sale-create.js:896-937`) and the `customerField.tomselect` branches in `setCustomer()` (513-520) and `saveNewCustomer()` (632-638) — replace with the new plain hidden-field + chip logic.
   - New-customer save flow: on success, set the hidden value + chip + meta directly (no `tomselect.addOption`).

3. **Remove band-aids** (only after Phase 1 verified working):
   - Delete the BFCache force-reload (`sale-create.js:15-21`).
   - Delete the TomSelect `z-index` override block (`sale-create.css:323-338`).

### Phase 2 — Lifecycle / reliability hardening

4. Confirm init is idempotent and order-independent: `initSaleCreate()` runs from `extra_js` (before theme `app.js`); verify no dependency on theme JS. Bootstrap modal + `bootstrap.Modal` are available (bundle loads in `base.html` head-order? No — bundle is at body end, before `extra_js`). **Verify** `bootstrap` global exists when `sale-create.js` runs; if not, guard modal creation. (base.html: bootstrap bundle line 98 runs before `extra_js` line 105, so OK — just confirm.)
5. Focus management: keep initial focus on product search; after selecting a customer, return focus to product search; after clearing cart / next sale, focus product search. Ensure `startNextSale()` resets the new customer chip to Walk-in.
6. Verify BFCache removal didn't reintroduce stale state: on normal `pageshow`, the in-memory `cart` and the DOM are both restored together, so they stay consistent; confirm no duplicate event listeners (init runs once per real load).

### Phase 3 — UX polish & visual consistency (CSS-light, reuse components)

7. Product search: already strong; add clearer empty/return states copy if needed. No structural change.
8. Payment/summary card: keep; ensure labels and feedback are clear (Grand total, Amount due/Change flip already exists).
9. Success feedback: existing success modal is good; ensure "Start next sale" fully resets (incl. customer chip) and refocuses search.
10. Validation messages: keep the non-blocking `#saleAlert` region (better than modals for cashier speed).
11. Visual alignment with Return page: consistent card headers, spacing (`mb-3`), and the shared `page_header` (already used). No bespoke redesign; reuse Bootstrap + existing `sale-create.css` classes. Fold any still-needed non-TomSelect rules; keep page-specific CSS in `sale-create.css`.
12. Bump the asset version (`sale-create.js?v=8`) so the cache busts.

### Backend (only if strictly necessary)

- **None expected.** All customer/product APIs already return what the new UI needs. Do **not** change `pos_checkout`, form fields, or API shapes. If the customer search needs phone display it is already present in `api_customer_search`.

---

## Files Affected

- `templates/sales/sale_form.html` — customer field markup swap; minor spacing polish.
- `static/js/sale-create.js` — replace TomSelect with custom customer search; remove BFCache reload; update `setCustomer`/`saveNewCustomer`; keep everything else.
- `static/css/sale-create.css` — remove TomSelect z-index block; add customer-chip/results styles (reuse `.sale-search*`/`.sale-result*` where possible).
- (version bump reference in `sale_form.html`).

No Python/view/URL/migration changes.

---

## Risks & Mitigations

- **Risk:** Breaking the `customer_id` POST contract. **Mitigation:** keep a hidden field named `customer`; verify `pos_checkout` still receives `customer_id` for both walk-in (empty) and selected customer.
- **Risk:** Removing BFCache reload resurfaces a stale-state bug. **Mitigation:** remove only after the custom customer dropdown replaces TomSelect (TomSelect was the stale element); manually test Back-button restore.
- **Risk:** TomSelect removal affects other pages. **Mitigation:** none — TomSelect stays globally loaded in `base.html` and is still used by `transfer_form`/`stockout_form`; only this page stops using it.
- **Risk:** Duplicate/lost event listeners after refactor. **Mitigation:** keep the single-IIFE, delegated-listener structure; init runs once.

---

## Validation Plan

Automated (existing safety net):
- `python manage.py check`
- `python manage.py test apps.sales` (POS checkout path/service tests must still pass).
- Render check: load `sales:sale_create` via test client (200) and assert the page no longer references TomSelect for the customer field and the hidden `customer` field is present.

Manual browser smoke test (cashier flow):
1. Page loads; product search auto-focused. No console errors.
2. Product search: type SKU/brand/category → results appear; ↑/↓ + Enter adds; click adds; barcode-style exact SKU + Enter adds. Add/qty/discount/remove all update totals.
3. Customer: default Walk-in. Search by name/phone → results (debounced, no stale flicker) → select shows chip + meta card (phone, outstanding due). Clear (×) → back to Walk-in.
4. New customer modal → save → auto-selected as customer with chip + meta.
5. Payment: enter amount / "Pay exact" → Amount due ↔ Change flips; pick payment method.
6. Complete Sale → success modal → Print receipt opens; Start next sale fully resets (cart empty, Walk-in, focus on search).
7. Back button (BFCache) → page usable without manual refresh; no dead dropdown; no z-index/click issues.
8. Mobile width: action bar sticky; customer + product dropdowns open above content and are clickable.
9. Keyboard shortcuts F2 (focus search), F4 (focus amount), Ctrl/Cmd+Enter (complete) still work.

---

## Out of Scope

- Site-wide redesign of other templates.
- Category/Brand filter dropdowns (deferred).
- Loyalty scheme backend (payload already handled if a future migration adds fields).
- Any change to `pos_checkout`, `SaleForm` fields, or customer/product API response shapes.
