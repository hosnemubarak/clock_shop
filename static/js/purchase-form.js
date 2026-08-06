let items = [];
let itemIndex = 0;

function updateLinePreview() {
    const qty = parseInt(document.getElementById('newQty').value) || 0;
    const price = parseFloat(document.getElementById('newPrice').value) || 0;
    const lineTotal = qty * price;
    document.getElementById('linePreview').textContent = window.CURRENCY_SYMBOL + lineTotal.toFixed(2);
}

function fetchCurrentStock() {
    const productSelect = document.getElementById('newProduct');
    const warehouseSelect = document.getElementById('newWarehouse');
    const productId = productSelect.value;
    const warehouseId = warehouseSelect.value;
    const stockInfoEl = document.getElementById('currentStockInfo');
    
    if (!productId || !warehouseId) {
        stockInfoEl.textContent = '';
        return;
    }

    const warehouseName = warehouseSelect.options[warehouseSelect.selectedIndex].text;

    stockInfoEl.innerHTML = '<i class="las la-spinner la-spin"></i> Checking current stock...';
    
    fetch(`/inventory/api/products/${productId}/stocks/?warehouse=${warehouseId}`)
        .then(response => response.json())
        .then(data => {
            let totalStock = 0;
            data.forEach(stock => {
                totalStock += stock.quantity;
            });
            if (totalStock > 0) {
                stockInfoEl.innerHTML = `<span class="text-success"><i class="las la-check-circle"></i> You have <strong>${totalStock}</strong> in stock at <strong>${warehouseName}</strong>.</span>`;
            } else {
                stockInfoEl.innerHTML = `<span class="text-warning"><i class="las la-exclamation-circle"></i> Currently out of stock at <strong>${warehouseName}</strong>.</span>`;
            }
        })
        .catch(error => {
            console.error('Error fetching stock:', error);
            stockInfoEl.textContent = 'Failed to check current stock.';
        });
}

function addItem() {
    const productSelect = document.getElementById('newProduct');
    const warehouseSelect = document.getElementById('newWarehouse');
    const qty = document.getElementById('newQty').value;
    const price = document.getElementById('newPrice').value;
    
    if (!productSelect.value) {
        showValidationModal('Please select a product.', 'Product Required');
        return;
    }
    
    if (!qty || parseInt(qty) < 1) {
        showValidationModal('Please enter a valid quantity greater than zero.', 'Invalid Quantity');
        return;
    }
    
    if (!price || parseFloat(price) <= 0) {
        showValidationModal('Please enter a valid purchase price.', 'Invalid Price');
        return;
    }
    
    // Support either native select or TomSelect
    let productSku = '';
    if (productSelect.tomselect) {
        const option = productSelect.tomselect.options[productSelect.value];
        productSku = option ? option.text : '';
    } else {
        const product = productSelect.options[productSelect.selectedIndex];
        productSku = product.dataset.sku || product.text;
    }
    
    const warehouse = warehouseSelect.options[warehouseSelect.selectedIndex];
    
    const item = {
        index: itemIndex++,
        product_id: productSelect.value,
        product_sku: productSku,
        warehouse_id: warehouseSelect.value,
        warehouse_name: warehouse.dataset.name || warehouse.text,
        quantity: parseInt(qty),
        unit_price: parseFloat(price)
    };
    
    items.push(item);
    renderItems();
    
    // Reset form
    if (productSelect.tomselect) {
        productSelect.tomselect.clear();
    } else {
        productSelect.value = '';
    }
    document.getElementById('newQty').value = '1';
    document.getElementById('newPrice').value = '';
    
    // Clear the stock info display
    fetchCurrentStock();
}

function removeItem(index) {
    items = items.filter(i => i.index !== index);
    renderItems();
}

function renderItems() {
    const tbody = document.getElementById('itemsBody');
    let html = '';
    let total = 0;
    
    items.forEach(item => {
        const lineTotal = item.quantity * item.unit_price;
        total += lineTotal;
        html += `
            <tr>
                <td>${item.product_sku}</td>
                <td>${item.warehouse_name}</td>
                <td>${item.quantity}</td>
                <td>${window.CURRENCY_SYMBOL}${item.unit_price.toFixed(2)}</td>
                <td>${window.CURRENCY_SYMBOL}${lineTotal.toFixed(2)}</td>
                <td>
                    <button type="button" aria-label="Remove item" class="btn btn-soft-danger btn-sm" onclick="removeItem(${item.index})">
                        <i class="las la-times"></i>
                    </button>
                </td>
                <input type="hidden" name="items" value='${JSON.stringify(item)}'>
            </tr>
        `;
    });
    
    tbody.innerHTML = html || '<tr><td colspan="6" class="text-center text-muted">No items added</td></tr>';
    document.getElementById('grandTotal').textContent = window.CURRENCY_SYMBOL + total.toFixed(2);
}

document.addEventListener('DOMContentLoaded', function() {
    const productSelect = document.getElementById('newProduct');
    const warehouseSelect = document.getElementById('newWarehouse');
    
    if (productSelect) productSelect.addEventListener('change', fetchCurrentStock);
    if (warehouseSelect) warehouseSelect.addEventListener('change', fetchCurrentStock);
    
    // If tomselect exists on product dropdown, we initialize it
    if (productSelect && typeof TomSelect !== 'undefined' && !productSelect.classList.contains('tomselected')) {
        new TomSelect('#newProduct', {
            placeholder: 'Search products...',
            create: false
        });
    }

    const form = document.getElementById('purchaseForm');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (items.length === 0) {
                e.preventDefault();
                showValidationModal('Please add at least one item to the purchase before saving.', 'No Items Added');
                return false;
            }
            
            // Validation passed — show a loading state and block double-submit.
            const btn = document.getElementById('submitBtn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<i class="las la-spinner la-spin"></i> Saving...';
            }
        });
    }
});
