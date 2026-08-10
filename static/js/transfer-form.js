let items = [];
let itemIndex = 0;
let stockData = {};

document.addEventListener('DOMContentLoaded', function() {
    // Initialize source warehouse change listener
    const sourceWarehouseSelect = document.querySelector('[name="source_warehouse"]');
    const destWarehouseSelect = document.querySelector('[name="destination_warehouse"]');

    function updateDestinationOptions() {
        if (!destWarehouseSelect || !sourceWarehouseSelect) return;
        const sourceId = sourceWarehouseSelect.value;
        
        Array.from(destWarehouseSelect.options).forEach(option => {
            if (option.value && option.value === sourceId) {
                option.disabled = true;
                if (destWarehouseSelect.value === sourceId) {
                    destWarehouseSelect.value = '';
                }
            } else {
                option.disabled = false;
            }
        });
    }

    if (sourceWarehouseSelect) {
        sourceWarehouseSelect.addEventListener('change', function() {
            loadWarehouseStocks(this.value);
            // Clear items when source warehouse changes
            items = [];
            renderItems();
            updateDestinationOptions();
        });
        
        // Load stocks if a source warehouse is already selected
        if (sourceWarehouseSelect.value) {
            loadWarehouseStocks(sourceWarehouseSelect.value);
            updateDestinationOptions();
        }
    }

    const form = document.getElementById('transferForm');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (items.length === 0) {
                e.preventDefault();
                showValidationModal('Please add at least one item to the transfer before submitting.', 'No Items Added');
                return false;
            }
            
            const source = document.querySelector('[name="source_warehouse"]').value;
            const dest = document.querySelector('[name="destination_warehouse"]').value;
            
            if (!source || !dest) {
                e.preventDefault();
                showValidationModal('Please select both source and destination warehouses.', 'Warehouse Required');
                return false;
            }
            
            if (source === dest) {
                e.preventDefault();
                showValidationModal('Source and destination warehouses must be different. Please select a different destination.', 'Invalid Selection');
                return false;
            }

            // Validation passed — show a loading state and block double-submit.
            const btn = document.getElementById('submitBtn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<i class="las la-spinner la-spin"></i> Creating...';
            }
        });
    }
    
    // Initial render
    renderItems();
});

function loadWarehouseStocks(warehouseId) {
    const stockSelect = document.getElementById('newStock');
    stockSelect.innerHTML = '<option value="">Loading...</option>';
    stockData = {};
    
    if (!warehouseId) {
        stockSelect.innerHTML = '<option value="">Select source warehouse first</option>';
        return;
    }
    
    fetch(`/warehouse/api/${warehouseId}/stocks/`)
        .then(response => response.json())
        .then(data => {
            stockSelect.innerHTML = '<option value="">Select Product</option>';
            if (data.length === 0) {
                stockSelect.innerHTML = '<option value="">No stock available</option>';
                return;
            }
            data.forEach(stock => {
                stockData[stock.product_id] = stock;
                let costStr = stock.average_cost !== null ? ` @ ${window.CURRENCY_SYMBOL}${stock.average_cost}` : '';
                stockSelect.innerHTML += `<option value="${stock.product_id}">${stock.product_sku} (${stock.quantity} avail${costStr})</option>`;
            });
            
            // Initialize Tom Select for searchable stock dropdown
            if (window.stockTomSelect) {
                window.stockTomSelect.destroy();
            }
            if (typeof TomSelect !== 'undefined') {
                window.stockTomSelect = new TomSelect('#newStock', {
                    placeholder: 'Search product...',
                    allowEmptyOption: true
                });
            }
        })
        .catch(error => {
            console.error('Error loading stocks:', error);
            stockSelect.innerHTML = '<option value="">Error loading stock</option>';
        });
}

function addItem() {
    const stockSelect = document.getElementById('newStock');
    const qtyInput = document.getElementById('newQty');
    const qty = parseInt(qtyInput.value);

    // Get stock value from Tom Select instance if it exists, otherwise from select element
    const productId = window.stockTomSelect ? window.stockTomSelect.getValue() : stockSelect.value;

    if (!productId) {
        showValidationModal('Please select a product before adding.', 'Product Required');
        return;
    }

    if (!qty || qty < 1) {
        showValidationModal('Please enter a valid quantity greater than zero.', 'Invalid Quantity');
        return;
    }
    
    const stock = stockData[productId];
    if (!stock) {
        showValidationModal('The selected product is invalid. Please refresh and try again.', 'Invalid Product');
        return;
    }
    
    if (qty > stock.quantity) {
        showValidationModal(`Only ${stock.quantity} units available. Please reduce the quantity.`, 'Insufficient Stock');
        return;
    }
    
    // Check if product already added
    const existingItem = items.find(i => i.product_id == productId);
    if (existingItem) {
        const newQty = existingItem.quantity + qty;
        if (newQty > stock.quantity + existingItem.quantity) {
            showValidationModal(`Only ${stock.quantity + existingItem.quantity} units available in total.`, 'Insufficient Stock');
            return;
        }
        existingItem.quantity = newQty;
    } else {
        const item = {
            index: itemIndex++,
            product_id: productId,
            product_sku: stock.product_sku,
            quantity: qty,
            buy_price: stock.average_cost
        };
        items.push(item);
    }
    
    stockData[productId].quantity -= qty;
    
    // Update the stock select option to show new available quantity
    if (window.stockTomSelect) {
        const s = stockData[productId];
        let costStr = s.average_cost !== null ? ` @ ${window.CURRENCY_SYMBOL}${s.average_cost}` : '';
        const newText = `${s.product_sku} (${s.quantity} avail${costStr})`;
        
        // Remove and re-add the option to avoid Tom Select errors
        window.stockTomSelect.removeOption(productId);
        window.stockTomSelect.addOption({value: productId, text: newText});
        window.stockTomSelect.refreshOptions(false);
    }
    
    renderItems();

    // Reset inputs
    if (window.stockTomSelect) {
        window.stockTomSelect.clear();
    } else {
        stockSelect.value = '';
    }
    qtyInput.value = '1';
}

function removeItem(index) {
    const item = items.find(i => i.index === index);
    if (item && stockData[item.product_id]) {
        stockData[item.product_id].quantity += item.quantity;
        
        // Update the stock select option
        if (window.stockTomSelect) {
            const s = stockData[item.product_id];
            let costStr = s.average_cost !== null ? ` @ ${window.CURRENCY_SYMBOL}${s.average_cost}` : '';
            const newText = `${s.product_sku} (${s.quantity} avail${costStr})`;
            
            // Remove and re-add the option to avoid Tom Select errors
            window.stockTomSelect.removeOption(item.product_id);
            window.stockTomSelect.addOption({value: item.product_id, text: newText});
            window.stockTomSelect.refreshOptions(false);
        }
    }
    items = items.filter(i => i.index !== index);
    renderItems();
}

function renderItems() {
    const tbody = document.getElementById('itemsBody');
    let html = '';
    let grandTotal = 0;
    
    items.forEach(item => {
        let totalValStr = '-';
        if (item.buy_price !== null) {
            const total = item.quantity * parseFloat(item.buy_price);
            grandTotal += total;
            totalValStr = `${window.CURRENCY_SYMBOL}${total.toFixed(2)}`;
        }
        html += `
            <tr>
                <td>
                    <strong>${item.product_sku}</strong>
                </td>
                <!-- No Batch cell -->
                <td class="text-center">${item.quantity}</td>
                <td class="text-end">${totalValStr}</td>
                <td class="text-center">
                    <button type="button" aria-label="Remove item" class="btn btn-soft-danger btn-sm" onclick="removeItem(${item.index})">
                        <i class="las la-times"></i>
                    </button>
                </td>
                <input type="hidden" name="items" value='${JSON.stringify(item).replace(/'/g, "&#39;")}'>
            </tr>
        `;
    });
    
    if (items.length > 0) {
        html += `
            <tr class="table-light">
                <td colspan="2" class="text-end fw-bold">Total Value:</td>
                <td class="text-end fw-bold">${window.CURRENCY_SYMBOL}${grandTotal.toFixed(2)}</td>
                <td></td>
            </tr>
        `;
    }
    
    if (tbody) {
        tbody.innerHTML = html || '<tr><td colspan="4" class="text-center text-muted py-3">No items added yet. Select a product and quantity above.</td></tr>';
    }
}
