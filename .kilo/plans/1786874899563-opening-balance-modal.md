# Opening Balance Modal

## Goal

Make the customer-detail page the primary Opening Balance workflow by moving the two-field form into the shared application modal system, while preserving `/customers/<pk>/opening-balance/` as the canonical endpoint and progressive-enhancement fallback.

## Decisions

- Primary entry point: permission-gated modal on `templates/customers/customer_detail.html`.
- Preserve the existing dedicated page and URL for direct links, bookmarks, no-JavaScript use, and non-modal fallback.
- Keep the existing endpoint, model fields, atomic save, balance recalculation, audit record, success message, and redirect behavior for normal form requests.
- Add an AJAX response branch to the same endpoint rather than creating a duplicate API view.
- Modal success behavior: update the visible opening-balance and total-due values, then reload customer detail to ensure all derived sections and statement links are fresh.
- Modal validation behavior: return field/non-field errors as JSON and render them inside the active modal; do not open a global validation modal over it.
- Future effective dates are rejected. Opening balance is immediate debt and must not appear in a future statement window while affecting current `total_due`.
- Lock and re-read the customer inside the transaction before capturing old values and saving, reducing concurrent opening-balance/payment recalculation races.
- Permission behavior for modal requests must return a generic JSON `403` response, not the existing stock-transfer-specific message.

## Implementation Steps

1. Strengthen opening-balance form validation.
   - Add a `clean_opening_balance_date()` check in `apps/customers/forms.py` that rejects dates after `timezone.localdate()` with a user-facing error.
   - Preserve zero as a valid amount and retain existing amount precision/minimum validation.
   - Add focused form tests for today, historical dates, future dates, zero, negative values, and missing dates.

2. Make the view support both normal and modal requests.
   - Update `apps/customers/views.py:opening_balance_set` to detect AJAX/JSON requests consistently with the project decorator convention.
   - Use `transaction.atomic()` with `Customer.objects.select_for_update().get(pk=pk)` before reading old values.
   - For valid modal requests, return JSON containing success status, customer ID, opening amount/date, and recalculated total due; preserve audit creation and recalculation.
   - For invalid modal requests, return status `400` with field error lists and non-field errors serialized from the bound form.
   - Preserve HTML GET/POST behavior and redirect/message behavior for normal requests.
   - Ensure missing customers remain `404` and authentication/permission semantics remain unchanged.

3. Make permission failures modal-safe.
   - Apply `json_for_ajax=True` to the opening-balance permission decorator or extend the decorator response without changing unrelated callers.
   - Return a generic message such as `You do not have permission to change opening balances.` with HTTP `403` for AJAX/JSON requests.
   - Add tests covering authorized modal success, invalid modal response, unauthorized modal response, anonymous redirect, and normal unauthorized redirect.

4. Add the customer-detail modal.
   - Replace the current opening-balance link in `templates/customers/customer_detail.html` with a button targeting a unique modal ID, preserving the permission condition and Set/Edit label.
   - Add a compact `.app-modal app-modal--form` shell with `role="dialog"`, `aria-modal`, unique `aria-labelledby`, accessible close button, customer context, explanation text, amount/date fields, inline error region, Cancel, and Save actions.
   - Keep the existing form field IDs/contracts where possible and associate every label with its input.
   - Expose stable data attributes or IDs for current opening amount/date and total due so the script can update or verify them before reload.
   - Keep the modal centered and compact; do not make this short two-field form fullscreen on mobile unless shared form rules require it.

5. Add page-level modal JavaScript.
   - Add a focused customer-detail script, preferably a new `static/js/customer-detail.js` loaded only by that template.
   - Initialize with `bootstrap.Modal.getOrCreateInstance()` and track the trigger for focus restoration through the existing modal conventions.
   - On open, reset stale error output and initialize the form from the rendered customer values.
   - Submit with `fetch()` to the existing opening-balance URL using CSRF headers and an AJAX marker/content type.
   - Disable the submit control and show a loading state during the request; restore it on every failure path.
   - Render JSON field errors next to the corresponding controls and summary errors in the modal error region.
   - Handle `403`, login HTML redirects, malformed/non-JSON responses, network errors, and unexpected server errors without leaving an orphaned backdrop.
   - On success, close the modal and reload the customer detail page so total due, opening-balance summary, invoices, and transaction sections stay consistent.

6. Preserve and normalize the dedicated fallback page.
   - Keep `templates/customers/opening_balance_form.html` and its route intact.
   - Apply shared form styling and label associations to the dedicated page where practical, without making it depend on JavaScript.
   - Retain its explanation, CSRF token, server-rendered validation errors, Save action, and Cancel link.

7. Add customer-detail and endpoint regression coverage.
   - Verify the trigger is rendered for users with `customers.set_opening_balance` and hidden for unauthorized users.
   - Verify the modal root has unique ID/ARIA attributes and both fields are present.
   - Verify valid JSON submission updates the customer, recalculates `total_due`, creates the expected audit record, and returns the expected payload.
   - Verify invalid JSON submission returns `400`, leaves customer values and audit logs unchanged, and includes field errors.
   - Verify future-date submissions are rejected for both HTML and JSON requests.
   - Verify normal HTML POST still redirects with the existing success message.
   - Verify permission failures use a generic JSON `403` for modal requests and preserve the existing unauthorized redirect for normal requests.
   - Verify `select_for_update()` is used in the write path and that unchanged submissions retain existing behavior unless a deliberate audit policy is introduced.

## Risks and Boundaries

- Do not create a second opening-balance persistence or calculation path.
- Do not convert payment entry into a modal; it remains a dedicated page because of its invoice allocation and validation complexity.
- Reload after success rather than trying to patch every customer-detail aggregate locally.
- Future-date rejection changes existing accepted input behavior and must be reflected in form and view tests.
- The existing test environment has previously returned HTTPS/host `301` redirects for sales tests; distinguish that environment issue from opening-balance failures.
- No browser harness exists, so responsive, Escape, close-button, focus restoration, backdrop, and retry behavior require manual browser validation.

## Validation Commands

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py test apps.customers.tests --verbosity 1`
- `node --check static/js/customer-detail.js`
- `git diff --check`
- Compile changed Django templates and manually verify the customer-detail modal at approximately 320px, 375px, 768px, and desktop widths.
