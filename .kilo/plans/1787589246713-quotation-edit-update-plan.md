# Quotation Edit/Update Plan

## Context and Decisions

- Quotations are managed by `apps.quotations`; the create screen is a JavaScript-driven JSON form using `quotation_form.html` and `static/js/quotation-create.js`.
- Existing list/detail/print/delete behavior must remain available and behaviorally unchanged.
- Editing will reuse the current quotation form and fields: title, quotation date, validity date, client name, phone, address, discount, notes, and line items.
- Editing will preserve the existing quotation number, status, and `created_by`; status changes are out of scope.
- Use Django's existing `quotations.change_quotation` permission for edit routes and edit links. Keep create permission for creation and the existing view/delete permissions for those actions.
- Quotation items are display/pricing references only and have no inventory impact, so an update can safely replace the complete item set inside one database transaction.

## Implementation Tasks

1. Extend `apps/quotations/urls.py` with a permission-protected edit page route and a separate JSON update endpoint, leaving `api/save/` unchanged for existing creation clients.
2. Update `apps/quotations/views.py`:
   - Add `quotation_edit(request, pk)` to load the quotation with its items/products and render the existing quotation form with edit context.
   - Add an update API using `@has_permission('quotations.change_quotation', json_for_ajax=True)` and `@transaction.atomic`.
   - Parse and validate the same payload shape used by create: require a title and at least one item, normalize dates/text, and preserve the existing product/custom-item behavior and pricing fields.
   - Lock the quotation with `select_for_update()` before mutation, update only editable header fields, delete existing `QuotationItem` rows, create the submitted rows, recalculate subtotal/total, and preserve quotation number/status/creator.
   - Keep malformed/unknown product handling consistent with the current save contract, but ensure invalid update input rolls back both header and item changes and returns the same JSON error shape used by the form.
   - Record an `UPDATE` audit log with the quotation identity and useful before/after summary, including total changes; do not alter delete audit behavior.
   - Avoid changing the existing create endpoint's URL, permission, response, or create audit event.
3. Reuse `templates/quotations/quotation_form.html` for both create and edit:
   - Render a dynamic page title/header and save button label from context.
   - Add edit-only data attributes for quotation id/update URL and a serialized initial quotation payload, including all item fields needed to rebuild product and custom rows.
   - Keep create defaults (`today`, empty fields/cart) unchanged.
   - Change success copy/actions dynamically between created and updated without removing the existing print, create-another, or view actions.
4. Extend `static/js/quotation-create.js`:
   - Detect create versus edit from the form data attributes.
   - Initialize title, client fields, dates, valid-until, discount, notes, and cart from server-provided edit data before the first render.
   - Submit to the create URL in create mode and update URL in edit mode using the existing JSON/CSRF pattern.
   - Preserve current product search, custom-item modal, cart controls, recalculation, validation, reset, network-error handling, and success modal behavior.
   - Use update-specific button/loading/success text while leaving create mode text and flow intact; after a successful edit, keep the quotation id/number for print/view links and make the primary navigation return to the updated quotation detail.
5. Add an `Edit` entry to quotation list and detail actions only when `perms.quotations.change_quotation` is present. Use the existing row-menu/page-header/button conventions and pen icon. Do not remove or rewrite the existing view, print, or delete entries/modals/forms.
6. Add focused quotation tests in a new `apps/quotations/tests/test_views.py` (and model tests only if needed):
   - Login and permission checks for edit page and update API, including denial without `change_quotation`.
   - Create endpoint still creates a quotation with its current response and audit action.
   - Edit page renders the shared form with correctly serialized existing header/item data, including custom items and removed-product references where applicable.
   - Successful update changes editable fields and completely replaces items, recalculates totals, preserves quotation number/status/creator, creates one `UPDATE` audit entry, and does not touch inventory.
   - Empty items, missing title, malformed JSON, and invalid update input leave the original quotation and items unchanged.
   - Existing detail, print, and delete routes continue to resolve and work against an edited quotation.
   - Run quotation tests plus the full Django test suite and `manage.py check`.

## Data and Failure Handling

- The update API must treat header and item writes as one atomic operation. `select_for_update()` prevents concurrent edits from overwriting each other based on stale data.
- The quotation number must never be regenerated: updating an existing instance retains its non-empty number through the model's save override.
- Totals must be computed from persisted updated item rows, with the order-level discount applied once. Item and order discount values remain non-negative and totals must not become negative.
- Existing rows should be deleted only after payload validation has established a non-empty item set; any exception during replacement must roll back the deletion and header update.
- Update authorization must be enforced server-side even if a user manually visits an edit URL or calls the JSON endpoint. UI hiding is only a presentation aid.
- No migration is expected because the model already provides the `change_quotation` permission automatically from the existing model permissions.

## Validation Checklist

- Verify create mode remains pixel/interaction consistent and retains its current URLs, wording, permissions, and success actions.
- Verify edit mode loads all saved values, supports adding/removing products and custom items, preserves numeric recalculation, and works on mobile layouts inherited from the shared form.
- Verify list/detail edit links are absent without permission and present with permission.
- Verify quotation number and status remain unchanged after edits and audit logs distinguish `CREATE`, `UPDATE`, and `DELETE`.
- Verify view, print, and delete behavior is unchanged before and after an edit.
- Run `python manage.py check` and `python manage.py test` (or the repository's configured test command).
