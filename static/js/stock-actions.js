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
        return window.getCsrfToken ? window.getCsrfToken() : '';
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

        var modal = bootstrap.Modal.getOrCreateInstance(byId('quickAddStockModal'));
        modal.show();
    }

    function submitQuickAddStock() {
        var productId = byId('qasProductId').value;
        var warehouseId = byId('qasWarehouse').value;
        var quantity = byId('qasQuantity').value;
        var unitPrice = byId('qasUnitPrice').value;
        var supplier = byId('qasSupplier').value;
        var purchaseDate = byId('qasPurchaseDate').value;
        var notes = byId('qasNotes').value;

        if (!warehouseId || !quantity || !unitPrice || !purchaseDate) {
            showModalError('quickAddStockError', 'Please fill out all required fields.');
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
                showModalError('quickAddStockError', data.error || 'Unable to add stock.', 'Error');
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        })
        .catch(function () {
            showModalError('quickAddStockError', 'An error occurred.');
            btn.innerHTML = originalText;
            btn.disabled = false;
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var modal = byId('quickAddStockModal');
        var form = byId('quickAddStockForm');
        if (!modal || !form) return;
        modal.addEventListener('show.bs.modal', function () {
            if (window.clearModalError) window.clearModalError('quickAddStockError');
        });
        form.addEventListener('click', function (event) {
            var button = event.target.closest('[data-qty-change]');
            if (button && window.changeQty) window.changeQty(button, Number(button.dataset.qtyChange));
        });
        byId('btnQuickAddStock').addEventListener('click', submitQuickAddStock);
    });

    // Keep the public functions for existing page triggers.
    window.openQuickAddStockModal = openQuickAddStockModal;
    window.submitQuickAddStock = submitQuickAddStock;
    window.getCsrfToken = window.getCsrfToken || getCsrfToken;
})(window, document);
