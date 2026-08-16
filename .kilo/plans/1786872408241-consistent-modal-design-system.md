# Consistent Modal Design System

## Goal

Create one coherent modal system across the application with shared structure, spacing, typography, buttons, close controls, form layouts, accessibility behavior, and adaptive desktop/mobile presentation. Preserve each workflow's existing business behavior while removing duplicate and invalid modal markup.

## Decisions

- Scope is comprehensive: visual styling, markup normalization, accessibility, focus behavior, duplicated-modal consolidation, invalid table placement, native dialog replacement, and responsive behavior.
- Use adaptive mobile behavior by modal type:
  - Short alerts and confirmations remain centered inset dialogs.
  - Long forms and transaction workflows become fullscreen below the small-screen breakpoint with internal scrolling and sticky footer actions.
- Success dialogs are dismissible through Escape and a close button. Keep static behavior only while an operation is actively processing, if needed.
- Continue using Bootstrap 5 modal primitives; introduce an application modal layer rather than adding a new modal library.
- Keep specialized workflow content, such as checkout totals, payment receipt actions, customer fields, staff fields, and stock-transfer warehouse rows, but place it inside shared modal shells and shared form/footer patterns.
- Use text-safe title/message updates in JavaScript. Do not inject caller-provided modal titles through `innerHTML`.
- Preserve current backend contracts and redirect/query-string behavior. Modal changes are presentation and client interaction changes only.

## Current Modal Families

1. **Global message/callback dialogs**
   - `templates/partials/modals.html`
   - `static/js/modals.js`
   - Validation, success, confirm, and destructive confirmation helpers.
2. **Sales transaction dialogs**
   - `saleConfirmModal`, `saleSuccessModal`, `newCustomerModal`, `stockTransferModal`
   - `templates/sales/sale_form.html`, `templates/partials/customer_modal.html`, `static/js/sale-create.js`, `static/css/sale-create.css`
3. **Payment success dialogs**
   - Duplicated `paymentSuccessModal` in payment list, customer detail, and sale detail templates.
4. **Quotation dialogs**
   - Custom item form, quotation success, quotation delete dialogs.
   - Resolve the duplicate `successModal` ID between quotation-specific markup and the global shared modal.
5. **Staff management dialogs**
   - Role, password, delete, and add staff forms in `templates/core/staff_list.html`.
6. **Inventory quick-add dialog**
   - `templates/includes/quick_add_stock_modal.html`, `static/js/stock-actions.js`.

## Design System

### Shared shell

- Add application-scoped modal classes, preferably in a dedicated global stylesheet loaded after `custom.css`, such as `.app-modal`, `.app-modal__content`, `.app-modal__header`, `.app-modal__body`, and `.app-modal__footer`.
- Keep Bootstrap `.modal`, `.modal-dialog`, `.modal-content`, and data attributes for behavior; use application classes for visual consistency.
- Standardize:
  - `modal-dialog-centered` for all dialogs unless a deliberately fullscreen workflow requires otherwise.
  - `role="dialog"`, `aria-modal="true"`, and unique `aria-labelledby` IDs on every modal root.
  - A consistent header with title, optional description/subtitle, and accessible close button.
  - A consistent content radius, border, shadow, background, and border color using existing theme variables where available.
  - Shared header/body/footer padding tokens and footer alignment.
  - `modal-dialog-scrollable` for long forms and staff/inventory workflows.
- Add semantic variants:
  - `.app-modal--info` or `.app-modal--validation`
  - `.app-modal--success`
  - `.app-modal--confirm`
  - `.app-modal--danger`
  - `.app-modal--form`
  - `.app-modal--transaction`
- Variants should change icon/accent/button intent only. Do not create separate spacing systems.

### Typography and spacing

- Use the existing application body/font stack and Bootstrap typography scale.
- Establish a small token set for modal title, supporting text, label, body, and helper text sizes; avoid per-template font-size overrides.
- Use one spacing rhythm for header, body sections, form groups, and footer button gaps.
- Remove one-off combinations such as `border-0 pb-0 px-4 pt-4`, large inline icon sizes, and arbitrary modal-specific padding where the shared shell can provide it.

### Buttons and controls

- Standardize footer order: secondary/cancel action first, primary or destructive action last on desktop; stack full-width on narrow screens where appropriate.
- Use consistent button height, icon spacing, loading state, disabled state, and focus ring.
- Use `btn-primary` for ordinary completion, `btn-success` only for explicit successful business completion, and `btn-danger` for destructive actions.
- Ensure close icons have `aria-label="Close"`, sufficient touch size, and visible focus styles.
- Replace inline `onclick` modal actions with data attributes or page-level event wiring where practical.

### Forms

- Normalize modal labels with `for`/`id` pairs, required indicators, validation message placement, and input grouping.
- Use a shared form layout class for two-column desktop fields that collapses to one column on phones.
- Use `modal-dialog-scrollable` and a footer that remains available for long forms.
- Keep server-rendered validation errors inside the form modal. Do not open a second validation modal over an active form; use an inline error summary or shared modal error region.
- Preserve password toggles, quantity steppers, dynamic transfer rows, and existing field IDs required by JavaScript.

### Responsive rules

- Short message/confirm dialogs: inset and centered at all sizes, with constrained width and comfortable horizontal padding.
- Long forms and transaction workflows: add `modal-fullscreen-sm-down` or equivalent below the project small-screen breakpoint, with a scrollable body and footer actions protected by safe-area padding.
- Ensure modal content cannot exceed viewport height and long error messages wrap without horizontal overflow.
- On mobile, stack footer buttons or give the primary action full width; retain a clear secondary dismissal action.
- Preserve the existing stock-transfer mobile behavior while moving its internals onto the shared shell.

## Implementation Plan

### 1. Establish shared modal CSS and markup conventions

- Add a global modal stylesheet or a clearly scoped modal section in the application stylesheet loaded after Bootstrap and `custom.css`.
- Define shell, variant, form, footer, focus, scroll, and responsive rules.
- Remove or supersede `.z-1060`/`.z-1070` ad hoc modal styling with a documented stacking strategy. Keep a deliberate high layer only for a message dialog shown above a workflow modal, or preferably prevent stacking by rendering errors inline.
- Standardize backdrop and body overflow behavior through Bootstrap configuration and shared helper initialization.

### 2. Refactor global message helpers

- Normalize the four global modal roots in `templates/partials/modals.html` with shared classes, complete ARIA attributes, consistent header/footer structure, and variant classes.
- Update `static/js/modals.js` to:
  - Set title text through `textContent` and toggle a known icon element instead of injecting title HTML.
  - Use `getOrCreateInstance()` consistently.
  - Track the invoking element and restore focus after dismissal when it remains connected.
  - Clear callback state on every close path.
  - Avoid opening a global validation modal when a page-specific form modal is active; expose a reusable inline-error utility or return a caller-provided error target.
  - Keep current global function names as the compatibility API for existing pages.
- Add robust guards for missing elements and instances.

### 3. Consolidate repeated success and payment dialogs

- Create reusable partials for generic success and payment-receipt success content, with caller-provided labels, URLs, and action visibility.
- Replace duplicated payment success markup in:
  - `templates/customers/payment_list.html`
  - `templates/customers/customer_detail.html`
  - `templates/sales/sale_detail.html`
- Preserve `print_payment` query behavior and URL cleanup, but replace inline hide handlers with delegated/page JavaScript.
- Resolve the quotation `successModal` duplicate ID by giving quotation’s workflow result a unique ID or routing it through the shared success component while preserving print/create-another/view actions.
- Add close buttons and dismissible behavior to success dialogs; retain action buttons and disable/restore them during active requests only.

### 4. Normalize sales and customer modals

- Apply the shared shell to `saleConfirmModal`, `saleSuccessModal`, `newCustomerModal`, and `stockTransferModal`.
- Preserve all existing IDs used by `sale-create.js` unless a coordinated selector update is required.
- Convert checkout and success dialogs to the shared transaction variant; keep checkout totals and status emphasis.
- Keep stock transfer fullscreen on small screens and move its existing product summary, stats, rows, error area, and footer into the shared spacing and button rules.
- Add label associations and shared form grouping to `templates/partials/customer_modal.html`.
- Replace validation-modal stacking during customer creation with an inline error summary inside `newCustomerModal` while keeping the global helper for non-form page messages.

### 5. Normalize quotation modals and native dialogs

- Apply shared form/transaction/danger variants to the custom item, quotation success, and delete workflows.
- Change custom-item fields to stack safely at the smallest breakpoint instead of forcing two narrow `col-6` controls.
- Replace quotation `alert()` and `confirm()` calls in `static/js/quotation-create.js` with the shared validation/danger helpers, preserving reset and save behavior.
- Remove the duplicate quotation success ID and ensure quotation-specific action wiring targets the correct modal instance.
- Move quotation list delete modal markup out of `<tbody>` and use one delegated modal or a single page-level delete modal populated from the clicked quotation. Preserve CSRF form submission and URL target.
- Normalize quotation detail delete modal to the same single destructive variant.

### 6. Normalize staff management modals

- Move role/password/delete modal roots out of the staff table body in `templates/core/staff_list.html`.
- Prefer one reusable modal per operation populated with the selected staff member, or reusable partials with unique IDs if the existing server-rendered action target is simpler.
- Preserve POST endpoints, CSRF fields, role choices, password visibility/strength behavior, and invalid add-staff POST reopening.
- Add unique labels, descriptions, form error regions, `modal-dialog-scrollable`, and adaptive fullscreen behavior for long forms.
- Replace the page-header string callback with a standard data-trigger or page-level listener.

### 7. Normalize quick-add stock modal

- Apply the shared form variant to `templates/includes/quick_add_stock_modal.html`.
- Add `aria-labelledby`, close-label, label associations, and mobile-safe form layout.
- Preserve global `stock-actions.js` compatibility initially, but replace inline modal submit/quantity handlers with delegated listeners or explicit initialization where feasible.
- Keep error feedback inside the form modal rather than stacking the global validation modal; preserve successful reload behavior unless a success confirmation is explicitly required by the existing workflow.

### 8. Audit all remaining modal and dialog paths

- Search for every `.modal`, `bootstrap.Modal`, `alert(`, `confirm(`, `showValidationModal`, `showSuccessModal`, `showConfirmModal`, and `showDangerModal` after migration.
- Confirm no duplicate IDs exist at runtime on quotation, staff, list, detail, and sale pages.
- Confirm no modal root remains inside a table section such as `<tbody>`.
- Confirm every modal title is associated through `aria-labelledby`, every close button is labelled, and every form control in migrated modals has an associated label.
- Confirm modal stacking is intentional and backdrop/focus behavior is stable.

## Tests and Validation

- Add template smoke assertions for shared modal classes, unique IDs, `aria-labelledby`, close labels, and absence of table-body modal roots.
- Add JavaScript or DOM-level tests if a browser harness is introduced; otherwise validate helper behavior with focused static checks and manual browser checks.
- Test global helpers for title/message updates, callback clearing, focus restoration, repeated opening, and missing-instance guards.
- Test quotation and payment success flows preserve their redirect/query-string behavior and action URLs.
- Test invalid staff POST reopens the add-staff modal with errors.
- Test AJAX form failures remain inside the active form modal and do not leave orphaned backdrops.
- Run `python manage.py check`, `python manage.py makemigrations --check --dry-run`, focused Django tests, and the full suite in a supported Python/Django environment.
- Use browser/device checks at approximately 320px, 375px, 768px, and desktop widths.
- Manually verify:
  - Global validation, success, confirm, and destructive dialogs.
  - New customer, quick stock, staff role/password/add, quotation custom item/delete/success, payment success, sale checkout/success, and stock transfer.
  - Escape, close icon, backdrop, Tab focus containment, return focus, long content scrolling, safe-area footer spacing, loading/disabled states, and repeated open/close cycles.

## Risks and Boundaries

- Do not alter backend validation, permission, payment, checkout, transfer, or deletion semantics.
- Preserve all JavaScript IDs that page scripts depend on, or update the scripts in the same change with tests.
- Moving repeated modals out of tables can change CSS selectors and Bootstrap trigger behavior; verify each action target after consolidation.
- Success dialogs have different action sets; use a shared shell/partial, not a single hardcoded message body.
- The project currently has no browser test harness. Manual responsive validation remains required unless one is added deliberately.
- Existing Python 3.14/Django 4.2 template test instrumentation may block render assertions; separate environment failures from application failures.
