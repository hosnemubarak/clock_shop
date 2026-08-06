let items = [];
let productSelect;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Tom Select for product
    productSelect = new TomSelect('#productSelect', {
        placeholder: 'Search products...',
        onChange: function(value) {
            loadStock(value);
        }
    });
    
    // Warehouse change handler
    const warehouseSelect = document.getElementById('id_warehouse');
    if (warehouseSelect) {
        warehouseSelect.addEventListener('change', function() {
            if (productSelect) productSelect.clear();
            document.getElementById('availableQty').value = '';
            document.getElementById('unitCost').value = '0';
            document.getElementById('stockInfo').innerHTML = '';
        });
    }

    // Form validation
    const form = document.getElementById('stockoutForm');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (items.length === 0) {
                e.preventDefault();
                showValidationModal('Please add at least one item before submitting', 'No Items Added');
                return false;
            }

            // Validation passed — show a loading state and block double-submit.
            const btn = document.getElementById('submitBtn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<i class="las la-spinner la-spin"></i> Processing...';
            }
        });
    }
});

function loadStock(productId) {
    const warehouseId = document.getElementById('id_warehouse').value;
    
    if (!productId || !warehouseId) {
        document.getElementById('availableQty').value = '';
        document.getElementById('unitCost').value = '0';
        return;
    }
    
    fetch(`/inventory/api/warehouses/${warehouseId}/stocks/?product=${productId}`)
        .then(response => response.json())
        .then(data => {
            if (data.length === 0) {
                document.getElementById('stockInfo').innerHTML = '<span class="text-warning">No stock available for this product in selected warehouse</span>';
                document.getElementById('availableQty').value = '0';
                document.getElementById('unitCost').value = '0';
            } else {
                const stock = data[0];
                document.getElementById('stockInfo').innerHTML = '';
                document.getElementById('availableQty').value = stock.quantity;
                document.getElementById('unitCost').value = stock.average_cost;
                document.getElementById('quantityInput').max = stock.quantity;
            }
        });
}

function addItem() {
    const productEl = document.getElementById('productSelect');
    const qtyEl = document.getElementById('quantityInput');
    
    const productId = productEl.value;
    const quantity = parseInt(qtyEl.value);
    const availableQty = parseInt(document.getElementById('availableQty').value) || 0;
    const unitCost = parseFloat(document.getElementById('unitCost').value) || 0;
    
    if (!productId || !quantity) {
        showValidationModal('Please select product and enter quantity', 'Missing Information');
        return;
    }
    
    if (quantity > availableQty) {
        showValidationModal(`Cannot remove more than available quantity (${availableQty})`, 'Insufficient Stock');
        return;
    }
    
    // Check if product already added
    const existingIndex = items.findIndex(i => i.product_id == productId);
    if (existingIndex >= 0) {
        const newQty = items[existingIndex].quantity + quantity;
        if (newQty > availableQty) {
            showValidationModal(`Total quantity would exceed available (${availableQty})`, 'Quantity Exceeded');
            return;
        }
        items[existingIndex].quantity = newQty;
    } else {
        items.push({
            product_id: productId,
            product_sku: productEl.options[productEl.selectedIndex].dataset.sku,
            quantity: quantity,
            unit_cost: unitCost,
            available: availableQty
        });
    }
    
    renderItems();
    
    // Reset form
    if (productSelect) productSelect.clear();
    qtyEl.value = 1;
    document.getElementById('availableQty').value = '';
    document.getElementById('unitCost').value = '0';
}

function removeItem(index) {
    items.splice(index, 1);
    renderItems();
}

function renderItems() {
    const tbody = document.getElementById('itemsTableBody');
    
    if (items.length === 0) {
        tbody.innerHTML = `<tr id="emptyRow">
            <td colspan="5" class="text-center text-muted py-4">No items added yet</td>
        </tr>`;
        document.getElementById('submitBtn').disabled = true;
    } else {
        tbody.innerHTML = '';
        items.forEach((item, index) => {
            const total = item.quantity * item.unit_cost;
            tbody.innerHTML += `<tr>
                <td>${item.product_sku}</td>
                <td class="text-center">${item.quantity}</td>
                <td class="text-end">${window.CURRENCY_SYMBOL}${item.unit_cost.toFixed(2)}</td>
                <td class="text-end">${window.CURRENCY_SYMBOL}${total.toFixed(2)}</td>
                <td class="text-center">
                    <button type="button" aria-label="Remove item" class="btn btn-sm btn-soft-danger" onclick="removeItem(${index})">
                        <i class="las la-trash"></i>
                    </button>
                </td>
            </tr>`;
        });
        document.getElementById('submitBtn').disabled = false;
    }
    
    updateSummary();
    document.getElementById('items_data').value = JSON.stringify(items);
}

function updateSummary() {
    const totalItems = items.length;
    const totalQty = items.reduce((sum, i) => sum + i.quantity, 0);
    const totalValue = items.reduce((sum, i) => sum + (i.quantity * i.unit_cost), 0);
    
    document.getElementById('summaryItems').textContent = totalItems;
    document.getElementById('summaryQty').textContent = totalQty;
    document.getElementById('summaryValue').textContent = window.CURRENCY_SYMBOL + totalValue.toFixed(2);
    document.getElementById('totalValue').textContent = window.CURRENCY_SYMBOL + totalValue.toFixed(2);
}
