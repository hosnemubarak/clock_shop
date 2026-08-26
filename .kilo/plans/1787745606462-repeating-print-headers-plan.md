# Repeating Print Headers Plan

## Context

- Sales invoices, quotations, and payment receipts use `static/css/print.css` and their own print templates:
  - `templates/sales/sale_print.html`
  - `templates/quotations/quotation_print.html`
  - `templates/customers/payment_print.html`
- Each document currently renders one full company header before the document banner. The item tables already use a `thead`, and the shared print CSS enables `thead { display: table-header-group; }`, so table headers repeat but the shop identity does not.
- Shop identity is already available to all three templates through the global context (`SHOP_NAME`, `SHOP_ADDRESS`, and `SHOP_LOGO`). No view, model, route, permission, or invoice-calculation changes are needed.
- The existing sales layout uses hard-coded brand text (`SKY ZONE INTERNATIONAL`) instead of `SHOP_NAME`; the requested repeated header must use the configured shop name consistently without changing unrelated invoice behavior.

## Decisions

- Apply the feature to all three print documents, as requested: sales invoice, quotation, and payment receipt.
- Keep page one’s existing full header, document banner, and invoice/receipt details unchanged in structure and visual hierarchy.
- Add a compact company identity row to each items table’s `thead`. It contains the configured logo, shop name, and address only, with a restrained height, border, and typography. Because it is inside `thead`, browsers repeat it above the table columns on continuation pages.
- Do not repeat invoice/quotation/receipt metadata on continuation pages; the compact identity row is sufficient and avoids wasting page space.
- Use deterministic client-side pagination for Chrome/Edge rather than relying on unsupported/inconsistent `counter(pages)`. Build page wrappers from the already-rendered table rows, calculate the final page count, and render exact `Page X of Y` labels into each wrapper. Keep pagination limited to the print view and preserve the original DOM for screen display.
- Show page labels only when the generated document has more than one page, matching the requirement; one-page documents show no `Page 1 of 1` label.
- Preserve the existing design tokens, fonts, colors, table column headings, watermark, totals, signatures, notes, and responsive screen layout. Only print-specific spacing/continuation-header rules may be adjusted.

## Implementation

1. Update all three print templates.
   - Mark the current full page-one content, items table, and final summary/bottom content with stable hooks used by the pagination script; keep the existing markup and data bindings intact.
   - Add a reusable compact continuation-header fragment to each template, using the same logo fallback logic and rendering `SHOP_NAME` plus `SHOP_ADDRESS|linebreaksbr` with the existing `Shop` fallback. Give it a meaningful logo alt text and ensure it contains no invoice metadata.
   - Add a page-number hook to each generated page wrapper, not a hard-coded page count. Keep the toolbar and navigation links unchanged.
   - Ensure table column counts remain correct for each document (five for sales/quotations, two for payments).

2. Update `static/css/print.css`.
   - Define screen-safe defaults for page wrappers, compact continuation headers, and page labels; make the generated page structure visible only for print while the original invoice remains the screen fallback.
   - Style each generated A4 page with the existing paper padding, colors, typography, and watermark treatment. Keep the first page’s full header/banner/details and use only the compact logo/name/address header on later pages.
   - Make the compact header horizontal, constrained, and non-breaking, with a small logo and clipped/wrapped address rules that cannot consume excessive continuation-page height.
   - Retain row and summary break protection, but remove dependence on native table-header repetition for the generated pages because the script explicitly inserts the compact header and column headings on every page.
   - Style the page label as a small, professional footer/header-adjacent element and render the supplied text `Page X of Y`; do not use CSS total-page counters.
   - Do not use fixed invoice heights or forced browser scaling. Use A4 dimensions and measured available content height only for pagination.

3. Add one shared print pagination script, loaded by all three print templates.
   - Wait until DOM content, fonts, and logo images have loaded before measuring. On screen, leave the existing invoice markup visible and do not run pagination.
   - In print preparation, create hidden measurement/page containers using the existing full header, details, table column headings, and final summary blocks. Fill page one first, then split item rows into later pages based on actual `scrollHeight`/`getBoundingClientRect()` measurements and the A4 content height.
   - Insert the compact continuation header and repeated column headings before rows on every page after page one. Keep each row intact; if a single row exceeds available height, allow it to wrap rather than dropping or duplicating it.
   - Keep totals, notes, signatures, and footer on the final page, moving them as a complete block when possible. Re-measure after adding the final block and create another page if required.
   - Once all pages are built, set every label to the final page count and replace the original print-only content with the generated pages. Use `beforeprint`/`afterprint` (or equivalent guarded preparation) so repeated print attempts rebuild cleanly and the screen DOM is restored after printing.
   - Avoid duplicating IDs or event handlers from cloned markup; the print page is static and must preserve all displayed values exactly.

4. Do not alter backend context generation or business logic.
   - The existing global context already supplies all required values and correctly supports database settings with environment fallbacks.
   - Do not introduce guessed item-count pagination. Let the browser paginate variable-height rows, addresses, notes, and totals using the existing break rules.

## Risks and Edge Cases

- Client-side pagination is sensitive to browser zoom, print margins, font loading, and image dimensions. Measure using the same CSS A4 content box used by print CSS, rebuild after fonts/images load, and keep a small safety allowance to avoid an extra blank page caused by rounding.
- Long shop addresses and large logos must be constrained in the compact row so they do not expand the repeated header enough to obscure table rows.
- Long product names, customer addresses, notes, and unusually large item lists must continue to wrap and paginate without clipping. Existing `break-inside: avoid` rules should remain in force for rows and summary blocks.
- One-page documents must retain the current professional appearance, with no compact continuation header, duplicate full header, or `Page 1 of 1` label.
- Missing shop logo/address must continue to use the existing fallback behavior.

## Validation

- Run `python manage.py check`.
- Run the relevant Django view tests for sales, quotations, and customers, and add focused response-content assertions if the current suites do not cover all three print routes. Verify the new compact header markup, configured identity values, and page-number markup are present without changing response status or permissions.
- Run `git diff --check`.
- In print preview, inspect a short one-page sales invoice, quotation, and payment receipt: the full page-one header remains intact, the compact row does not create an obvious duplicate, and page numbering is hidden or appropriately presented according to the chosen print-counter behavior.
- Inspect multi-page sales invoice, quotation, and payment receipt fixtures in Chrome/Edge print preview: every continuation page starts with logo, shop name, address, and column headings; rows are not clipped; totals/signatures/notes remain together where possible; and the page label reads `Page 1 of N`, `Page 2 of N`, etc. with the actual total.
- Test missing logo/address and long multi-line address values.
- Confirm the non-print browser view is unchanged and print toolbar/navigation remain hidden during printing.

## Scope

- Modify only the three print templates, the shared print stylesheet, one shared print-pagination script, plus narrowly scoped print-view tests if needed.
- Do not change quotation, payment, or sales data behavior, calculations, URLs, permissions, or unrelated site styles.
