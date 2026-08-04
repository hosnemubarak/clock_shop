# Sales Create — "Dead Until Refresh" First-Load Fix

Plan ID: 1785777433361
Scope: **Sales Create page only** (`/sales/create/`). One-line template change. No JS, no CSS, no backend.

---

## Symptom

On first navigation to `/sales/create/`, the page is not interactive — customer search,
product search, and other controls do nothing until the user manually refreshes. After a
refresh the page works normally.

## Root Cause (verified against code)

The Velzon theme persists the **first visited page's** `<html>` layout attributes into
`sessionStorage` under the key `defaultAttribute` (written by `static/js/app.js`).

`static/js/layout.js` runs **synchronously in `<head>`** (before the body renders). It rebuilds
an object from the current `<html>` attributes and compares it to the stored `defaultAttribute`
snapshot. On **any mismatch** it executes:

```js
sessionStorage.clear();
window.location.reload();
```

`templates/sales/sale_form.html:6` is the **only** template in the entire project that overrides
a layout attribute:

```django
{% block sidebar_size %}sm{% endblock %}
```

Every other page inherits the base default `data-sidebar-size="lg"` from
`templates/base.html:3`. So arriving at `/sales/create/` from any normal page (dashboard, lists,
etc.) produces `sm` ≠ stored `lg` → `layout.js` force-reloads the page in the head. On that
forced reload the snapshot was just cleared, so no further reload fires and the page finally
becomes usable — which is exactly the "broken until I refresh" behavior. The user's manual
refresh and the theme's automatic reload are the same recovery.

Two corroborating facts:

- The `sm` override is **non-functional anyway**: `app.js` re-applies the sidebar size *from
  `sessionStorage`* over whatever the HTML declared, so `sm` never visually sticks. It only ever
  triggers the reload machinery.
- A previous BFCache `window.location.reload()` band-aid lived in `sale-create.js` and was
  removed in the prior session; it had been masking this same theme-reload behavior. Its removal
  left the true cause exposed.

## Evidence

- `templates/base.html:3` — `data-sidebar-size="{% block sidebar_size %}lg{% endblock %}"` (app-wide default).
- `templates/sales/sale_form.html:6` — `{% block sidebar_size %}sm{% endblock %}` (the ONLY override in the project; confirmed by full-tree search).
- `static/js/layout.js` — head script: builds attr object from `document.documentElement`, compares to `sessionStorage` `defaultAttribute`, and on mismatch runs `sessionStorage.clear(); window.location.reload()`.
- `static/js/app.js` — writes `defaultAttribute` + per-attribute keys to `sessionStorage`; re-applies `data-sidebar-size` from storage (10 `setItem('data-sidebar-size', …)` sites), which is why the `sm` HTML value is overridden at runtime.
- `static/js/sale-create.js` — init path itself is sound: guarded `document.readyState` check (lines ~1094-1098), listeners attached before modal init; the page fails only because the theme reloads it out from under the first parse.

## Decision (resolved with user)

Remove the override so the sale page renders identical layout attributes to every other page.
The compact sidebar was never actually applied, so nothing visual is lost.

---

## Implementation Tasks

1. **Edit `templates/sales/sale_form.html`** — delete the sidebar-size override block.

   Remove line 6 (and its surrounding blank line) so the top of the file goes from:

   ```django
   {% block title %}New Sale | {{ SHOP_NAME }}{% endblock %}

   {% block sidebar_size %}sm{% endblock %}

   {% block extra_css %}
   ```

   to:

   ```django
   {% block title %}New Sale | {{ SHOP_NAME }}{% endblock %}

   {% block extra_css %}
   ```

   The page will then inherit `data-sidebar-size="lg"` from `base.html`, matching every other
   page. No other lines change.

That is the entire code change.

---

## Files Affected

- `templates/sales/sale_form.html` — remove the `{% block sidebar_size %}sm{% endblock %}` line.

No JavaScript, CSS, Python, view, URL, or migration changes. Do **not** re-add any
`pageshow`/BFCache `location.reload()` workaround — that is the temporary fix this plan
explicitly replaces with the real cause.

---

## Risks & Mitigations

- **Risk:** The compact sidebar was a deliberate POS space-saving choice. **Mitigation:** It was
  non-functional (overridden by `app.js` from `sessionStorage`), so removing it changes nothing
  the user actually saw. If a compact sidebar is later wanted here, it must be driven through the
  theme's own toggle/`sessionStorage` mechanism after theme init — never via a server-rendered
  `<html>` attribute that `layout.js` will treat as a mismatch.
- **Risk:** Another page later introduces a different layout-attribute override and reintroduces
  the reload. **Mitigation:** none needed now; note in review that per-page overrides of any
  `data-layout*` / `data-sidebar*` attribute will trigger the same theme reload.

---

## Validation Plan

Because the failure is a session-state interaction, test in a browser session, not just a single
page load:

1. **Reproduce first** (before the change, optional sanity): open the dashboard, then click
   through to `/sales/create/`; observe the page reload/flash and dead controls until refresh.
2. `python manage.py check` — sanity (no template/syntax breakage). Expected: no issues.
3. Existing `apps.sales` view tests still pass (the render-path test `test_page_renders` /
   `test_customer_field_is_a_plain_hidden_input` must stay green): `python manage.py test apps.sales`.
   Expected: same result as baseline (the only known failures are the pre-existing `tax_amount`
   errors in `test_payments.py`, unrelated to this change).
4. **Manual browser smoke (the real check):**
   - Clear the browser session (or use a fresh private window so `sessionStorage` is empty).
   - Visit the dashboard first, then navigate to `/sales/create/` via a normal link.
   - Confirm the page does **not** auto-reload/flash and that product search, customer search,
     payment inputs, and buttons are all interactive on that first arrival — no manual refresh.
   - Navigate away to another page and back to `/sales/create/` again; confirm it stays usable
     with no reload each time.
   - Confirm the sidebar looks the same as on every other page (expected: `lg`, since `sm` never
     applied).

---

## Out of Scope

- Any change to `layout.js` / `app.js` (theme vendor files).
- Introducing a real compact-sidebar-per-page feature.
- Any backend, form, URL, or migration change.
- The broader UI-standardization effort (separate initiative).
