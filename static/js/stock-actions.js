/**
 * Quick Add Stock — shared modal logic for product_list and product_detail.
 *
 * Both pages embed the same #quickAddStockModal markup and previously carried a
 * verbatim copy of this code. Keep the markup in sync; this file is the single
 * source of behavior.
 *
 * Depends on: bootstrap (Modal), modals.js (showValidationModal).
 */
(function (window, document) {
    'use strict';

    /**
     * Read the CSRF token. Prefers the hidden form input rendered by
     * {% csrf_token %}; falls back to the csrftoken cookie.
     */
    function getCsrfToken() {
        var field = document.querySelector('[name=csrfmiddlewaretoken]');
        if (field && field.value) {
            return field.value;
        }
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function byId(id) {
        return document.getElementById(id);
    }

    function openQuickAddStockModal(productId, productName, averageCost) {
        byId('qasProductId').value = productId;
        byId('qasProductName').textContent = productName;
        byId('qasUnitPrice').value = averageCost;
        byId('qasQuantity').value = '';
        byId('qasWarehouse').value = '';
        byId('qasSupplier').value = '';
        byId('qasPurchaseDate').value = new Date().toISOString().split('T')[0];
        byId('qasNotes').value = '';

        new bootstrap.Modal(byId('quickAddStockModal')).show();
    }

    function submitQuickAddStock() {
        var productId = byId('qasProductId').value;
        var warehouseId = byId('qasWarehouse').value;
        var quantity = byId('qasQuantity').value;
        var unitPrice = byId('qasUnitPrice').value;
        var supplier = byId('qasSupplier').value;
        var purchaseDate = byId('qasPurchaseDate').value;
        var notes = byId('qasNotes').value;

        if (!warehouseId || !quantity || !unitPrice || !supplier || !purchaseDate) {
            showValidationModal('Please fill out all required fields.');
            return;
        }

        var btn = byId('btnQuickAddStock');
        var originalText = btn.innerHTML;
        btn.innerHTML = '<i class="las la-spinner la-spin"></i> Adding...';
        btn.disabled = true;

        fetch('/inventory/api/products/' + productId + '/quick-add-stock/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                warehouse_id: warehouseId,
                quantity: quantity,
                unit_price: unitPrice,
                supplier: supplier,
                purchase_date: purchaseDate,
                notes: notes
            })
        })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            if (data.success) {
                window.location.reload();
            } else {
                showValidationModal(data.error, 'Error');
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        })
        .catch(function () {
            showValidationModal('An error occurred.', 'Error');
            btn.innerHTML = originalText;
            btn.disabled = false;
        });
    }

    // Exposed globally because the modal markup uses inline onclick handlers.
    window.openQuickAddStockModal = openQuickAddStockModal;
    window.submitQuickAddStock = submitQuickAddStock;
    window.getCsrfToken = window.getCsrfToken || getCsrfToken;
})(window, document);
