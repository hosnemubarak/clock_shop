# Sales Print Layout Plan

## Context

- The Sales invoice at `/sales/<id>/print/` uses `templates/sales/sale_print.html` and `static/css/print.css`.
- The invoice currently spills to a second A4 page despite unused vertical space on page one.
- The template structure and visual design are already appropriate; the main issue is cumulative print spacing and padding.
- No data, invoice content, or screen layout changes are required.

## Implementation

1. Update the `@media print` rules in `static/css/print.css` only.
   - Keep `@page { size: A4; }` and avoid changing the screen view.
   - Reduce print-only `.invoice-paper` top/bottom padding and retain reasonable horizontal margins.
   - Compact print-only header, document banner, bill-to/meta block, table header/cells, totals rows, and bottom sections.
   - Reduce signature vertical space and surrounding margins while preserving all three signature lines.
   - Reduce footer spacing and typography only as needed to fit the invoice naturally.
2. Preserve existing print safeguards.
   - Keep the toolbar hidden during printing.
   - Keep table headers repeating and rows/summary sections protected from awkward internal breaks.
   - Keep colors, borders, typography family, invoice content, and customer/payment information unchanged unless a small print-only size adjustment is necessary.
3. Avoid forced scaling or fixed invoice heights.
   - The layout should fit normal invoices on one A4 page through spacing optimization.
   - Longer notes, long customer addresses, or unusually large item lists may legitimately require a second page.
   - Ensure multi-page invoices remain readable and do not clip content.

## Validation

- Run `python manage.py check`.
- Run relevant Sales tests, especially invoice/detail/print rendering tests if present.
- Run `git diff --check`.
- Validate the print route with a representative short invoice such as `/sales/41/print/`: preview should fit on one A4 page with no clipped footer or signatures.
- Validate a longer invoice and a long-notes/customer case to confirm content flows to a second page safely when one page is not possible.
- Confirm the non-print browser view remains visually unchanged and the print toolbar remains hidden.

## Scope

- Modify only print-specific CSS unless a concrete rendering issue requires a minimal template adjustment.
- Do not change Sales calculations, invoice data, routes, permissions, or unrelated templates/styles.
