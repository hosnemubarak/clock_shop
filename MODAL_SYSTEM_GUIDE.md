# Modal System Guide

## Overview
This project uses a standardized modal system with consistent design across all pages. All modals are defined globally in `templates/partials/modals.html` and included in the base template.

## Available Modals

### 1. Validation/Error Modal (`validationModal`)
**Purpose:** Display validation errors, warnings, and general error messages.

**Usage:**
```javascript
showValidationModal(message, title = 'Validation Error');
```

**Example:**
```javascript
showValidationModal('Please enter a valid quantity', 'Invalid Input');
```

**Design:**
- Header: Warning color (bg-warning-subtle, text-warning)
- Icon: Exclamation triangle
- Button: Primary "OK" button

---

### 2. Success Modal (`successModal`)
**Purpose:** Display success messages and confirmations.

**Usage:**
```javascript
showSuccessModal(message, title = 'Success');
```

**Example:**
```javascript
showSuccessModal('Item added successfully', 'Success');
```

**Design:**
- Header: Success color (bg-success-subtle, text-success)
- Icon: Check circle
- Button: Success "OK" button

---

### 3. Confirmation Modal (`confirmModal`)
**Purpose:** Ask for user confirmation before performing an action.

**Usage:**
```javascript
showConfirmModal(message, title, callback);
```

**Example:**
```javascript
showConfirmModal(
    'Are you sure you want to complete this transfer?',
    'Confirm Transfer',
    function() {
        document.getElementById('transferForm').submit();
    }
);
```

**Design:**
- Header: Primary color (bg-primary-subtle, text-primary)
- Icon: Question circle
- Buttons: "Cancel" (light) and "Confirm" (primary)

---

### 4. Danger/Delete Modal (`dangerModal`)
**Purpose:** Confirm dangerous actions like deletions or cancellations.

**Usage:**
```javascript
showDangerModal(message, title, callback);
```

**Example:**
```javascript
showDangerModal(
    'Are you sure you want to delete this item? This action cannot be undone.',
    'Delete Item',
    function() {
        document.getElementById('deleteForm').submit();
    }
);
```

**Design:**
- Header: Danger color (bg-danger-subtle, text-danger)
- Icon: Exclamation triangle
- Buttons: "Cancel" (light) and "Confirm" (danger with trash icon)

---

## Design Standards

### Modal Structure
All modals follow this consistent structure:
```html
<div class="modal fade" id="modalId" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header bg-{color}-subtle">
                <h5 class="modal-title text-{color}" id="modalTitle">
                    <i class="las la-{icon} me-1"></i> Title
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body" id="modalBody">
                <!-- Message content -->
            </div>
            <div class="modal-footer">
                <!-- Action buttons -->
            </div>
        </div>
    </div>
</div>
```

### Color Scheme
- **Validation/Warning:** `bg-warning-subtle` + `text-warning`
- **Success:** `bg-success-subtle` + `text-success`
- **Confirmation:** `bg-primary-subtle` + `text-primary`
- **Danger/Delete:** `bg-danger-subtle` + `text-danger`

### Icons (Line Awesome)
- **Warning:** `las la-exclamation-triangle`
- **Success:** `las la-check-circle`
- **Question:** `las la-question-circle`
- **Delete:** `las la-trash`
- **Close:** `las la-times`
- **Confirm:** `las la-check`

### Buttons
- **Primary Action:** `btn btn-primary` or `btn btn-success` or `btn btn-danger`
- **Cancel/Close:** `btn btn-light`
- All buttons include icons for better UX

---

## Migration from Alerts

### Before (Old Way - DON'T USE)
```javascript
alert('Please enter a valid quantity');
confirm('Are you sure you want to delete this?');
```

### After (New Way - USE THIS)
```javascript
showValidationModal('Please enter a valid quantity', 'Invalid Input');

showDangerModal(
    'Are you sure you want to delete this?',
    'Confirm Delete',
    function() {
        // Delete action
    }
);
```

---

## Best Practices

1. **Always use modals instead of browser alerts**
   - Never use `alert()`, `confirm()`, or `prompt()`
   - Use the appropriate modal function instead

2. **Choose the right modal type**
   - Validation errors → `showValidationModal()`
   - Success messages → `showSuccessModal()`
   - General confirmations → `showConfirmModal()`
   - Dangerous actions → `showDangerModal()`

3. **Provide clear, concise messages**
   - Keep titles short and descriptive
   - Messages should explain what happened or what will happen
   - For confirmations, explain the consequences

4. **Use callbacks for confirmations**
   - Always provide a callback function for confirm/danger modals
   - The callback executes when user clicks "Confirm"

5. **Accessibility**
   - All modals include `aria-hidden="true"`
   - Close buttons have `aria-label="Close"`
   - Modals are centered with `modal-dialog-centered`

---

## Custom Modals

If you need a custom modal for a specific page (e.g., batch selection in POS), follow the same design standards:

```html
<div class="modal fade" id="customModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header bg-primary-subtle">
                <h5 class="modal-title text-primary">
                    <i class="las la-icon me-1"></i> Title
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <!-- Custom content -->
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-light" data-bs-dismiss="modal">
                    <i class="las la-times me-1"></i> Close
                </button>
            </div>
        </div>
    </div>
</div>
```

---

## Files Modified

### Core Files
- `templates/partials/modals.html` - Global modal definitions and JavaScript functions
- `templates/base.html` - Includes modals.html

### Updated Pages
- `templates/warehouse/transfer_form.html` - Uses validation modal
- `templates/warehouse/transfer_detail.html` - Uses confirmation modal
- `templates/sales/sale_form.html` - Uses validation modal
- `templates/sales/sale_detail.html` - Uses validation and confirmation modals
- `templates/sales/pos.html` - Uses validation modal, standardized batch modal
- `templates/inventory/purchase_form.html` - Uses validation modal
- `templates/inventory/stockout_form.html` - Uses validation modal
- `templates/inventory/stockout_detail.html` - Uses danger modal

---

## Testing Checklist

- [ ] All validation errors display in modals (no browser alerts)
- [ ] All confirmations use modal dialogs
- [ ] Modal design is consistent across all pages
- [ ] Modals are responsive and centered
- [ ] Close buttons work properly
- [ ] Callback functions execute correctly
- [ ] Icons display correctly
- [ ] Colors match the design system
- [ ] Accessibility attributes are present

---

## Troubleshooting

**Modal doesn't show:**
- Ensure `templates/partials/modals.html` is included in base template
- Check that Bootstrap JavaScript is loaded
- Verify function name is spelled correctly

**Callback doesn't execute:**
- Ensure callback is passed as a function, not a string
- Check browser console for JavaScript errors
- Verify form IDs match

**Styling looks wrong:**
- Ensure Bootstrap 5.3+ is loaded
- Check that Line Awesome icons are available
- Verify class names match the design system
