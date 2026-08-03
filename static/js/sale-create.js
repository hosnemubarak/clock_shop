/**
 * Sale screen (sales/create/).
 *
 * One IIFE, no globals, no inline handlers. The page holds no state of its own:
 * `cart` is the single source of truth and `render()` is the only thing that
 * writes to the DOM, so a bug can only ever produce one wrong number.
 *
 * Money is handled as integer minor units (paisa) everywhere. Floats accumulate
 * error across a long cart -- 0.1 + 0.2 !== 0.3 -- and this arithmetic ends up
 * in an invoice, so it never touches a fractional Number.
 */
console.log('[SaleCreate] Script loaded, attaching listeners...');

window.addEventListener('error', function(e) {
    console.error('[SaleCreate] JS Error: ', e.message, 'at', e.filename, ':', e.lineno);
    alert('JS Error: ' + e.message + ' at ' + e.filename + ':' + e.lineno);
});

function initSaleCreate() {
    'use strict';
    console.log('[SaleCreate] initSaleCreate() executing...');

    // Force reload if page is restored from BFCache (e.g. user clicked browser Back button).
    // This ensures TomSelect and the cart state do not break or become stale.
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            window.location.reload();
        }
    });

    var page = document.getElementById('salePage');
    if (!page) {
        console.warn('[SaleCreate] #salePage not found, aborting initialization.');
        return;
    }
    console.log('[SaleCreate] #salePage found, loading CFG...');

    var CFG = {
        searchUrl: page.dataset.searchUrl,
        checkoutUrl: page.dataset.checkoutUrl,
        customerSearchUrl: page.dataset.customerSearchUrl,
        customerCreateUrl: page.dataset.customerCreateUrl,
        customerInfoUrl: page.dataset.customerInfoUrl,
        receiptUrl: page.dataset.receiptUrl,
        saleListUrl: page.dataset.saleListUrl,
        currency: page.dataset.currency || ''
    };

    var SEARCH_DEBOUNCE_MS = 180;
    var MIN_QTY = 1;

    // ---------------------------------------------------------------- helpers

    /** Cached element lookups: the old page re-queried the same ids on every keystroke. */
    var el = {};
    ['productSearch', 'searchResults', 'searchSpinner', 'searchStatus',
     'cartBody', 'cartEmpty', 'cartCount', 'sumSubtotal', 'sumGrand', 'sumDue',
     'dueLabel', 'orderDiscount', 'amountPaid', 'paymentMethod',
     'saleAlert', 'saleAlertText', 'btnComplete', 'btnReset', 'customerMetaBox',
     'customerMetaName', 'customerMetaExtra', 'customerLoyaltyBox', 'customerLoyalty',
     'saleSuccessModal', 'successInvoice', 'btnPrintReceipt', 'btnNextSale',
     'linkViewSale', 'newCustomerModal', 'newCustomerForm', 'newCustomerName',
     'newCustomerPhone', 'newCustomerEmail', 'newCustomerAddress',
     'newCustomerSaveBtn'
    ].forEach(function (id) {
        el[id] = document.getElementById(id);
        if (!el[id]) console.warn('[SaleCreate] Warning: Missing DOM element: ' + id);
    });
    console.log('[SaleCreate] Finished gathering DOM elements.');

    var customerField = document.querySelector('[name="customer"]');
    var saleDateField = document.querySelector('[name="sale_date"]');
    var notesField = document.querySelector('[name="notes"]');
    var csrfToken = (document.querySelector('[name="csrfmiddlewaretoken"]') || {}).value || '';

    var money = new Intl.NumberFormat(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });

    /** Minor units -> "৳1,234.50". */
    function fmt(minor) {
        return CFG.currency + money.format(minor / 100);
    }

    /** "12.34" -> 1234. Rounds half-up at the last paisa; junk becomes 0. */
    function toMinor(value) {
        var n = parseFloat(value);
        if (!isFinite(n) || n < 0) {
            return 0;
        }
        return Math.round(n * 100);
    }

    function toMajor(minor) {
        return (minor / 100).toFixed(2);
    }

    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /** Escapes first, then wraps query hits in <mark> on the already-safe string. */
    function highlight(text, query) {
        var safe = escapeHtml(text);
        if (!query) {
            return safe;
        }
        var needle = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return safe.replace(new RegExp('(' + needle + ')', 'ig'), '<mark>$1</mark>');
    }

    function showAlert(message) {
        el.saleAlertText.textContent = message;
        el.saleAlert.hidden = false;
        el.saleAlert.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    function clearAlert() {
        el.saleAlert.hidden = true;
        el.saleAlertText.textContent = '';
    }

    // ------------------------------------------------------------------ state

    var cart = [];      // [{ productId, sku, label, unitPrice, qty, discount, stock }]
    var results = [];   // last search payload
    var activeIndex = -1;
    var submitting = false;
    var searchTimer = null;
    var searchAbort = null;
    var successModal = null;
    var customerModal = null;
    var lastSaleId = null;

    // ----------------------------------------------------------------- search

    function closeResults() {
        el.searchResults.hidden = true;
        el.searchResults.innerHTML = '';
        el.productSearch.setAttribute('aria-expanded', 'false');
        el.productSearch.removeAttribute('aria-activedescendant');
        results = [];
        activeIndex = -1;
    }

    function renderResults(query) {
        if (!results.length) {
            el.searchResults.innerHTML =
                '<li class="sale-search__message">No products match &ldquo;' +
                escapeHtml(query) + '&rdquo;.</li>';
            el.searchResults.hidden = false;
            el.productSearch.setAttribute('aria-expanded', 'true');
            el.searchStatus.textContent = 'No products found.';
            return;
        }

        el.searchResults.innerHTML = results.map(function (row, i) {
            var out = row.shop_stock <= 0;
            var meta = [row.brand, row.category].filter(Boolean).join(' &middot; ');
            var stockBadge = out
                ? '<span class="badge bg-danger-subtle text-danger">Out of stock</span>'
                : '<span class="badge bg-success-subtle text-success">' + row.shop_stock + ' in shop</span>';

            return '' +
                '<li class="sale-result' + (out ? ' is-disabled' : '') + (i === activeIndex ? ' is-active' : '') + '"' +
                ' id="saleResult' + i + '" role="option" data-index="' + i + '"' +
                ' aria-selected="' + (i === activeIndex ? 'true' : 'false') + '"' +
                ' aria-disabled="' + (out ? 'true' : 'false') + '">' +
                    '<div class="sale-result__body">' +
                        '<div class="sale-result__title">' + highlight(row.display_name, query) + '</div>' +
                        '<div class="sale-result__meta">' +
                            highlight(row.sku, query) + (meta ? ' &middot; ' + highlight(meta, query) : '') +
                        '</div>' +
                    '</div>' +
                    '<div class="sale-result__side">' +
                        '<div class="sale-result__price">' + fmt(toMinor(row.price)) + '</div>' +
                        '<div class="small">' + stockBadge + '</div>' +
                    '</div>' +
                '</li>';
        }).join('');

        el.searchResults.hidden = false;
        el.productSearch.setAttribute('aria-expanded', 'true');
        el.searchStatus.textContent = results.length + ' product' +
            (results.length === 1 ? '' : 's') + ' found.';
    }

    function setActive(index) {
        if (!results.length) {
            return;
        }
        // Wraps, so holding Down never dead-ends at the bottom of a long list.
        activeIndex = (index + results.length) % results.length;

        Array.prototype.forEach.call(
            el.searchResults.querySelectorAll('.sale-result'),
            function (node, i) {
                var on = i === activeIndex;
                node.classList.toggle('is-active', on);
                node.setAttribute('aria-selected', on ? 'true' : 'false');
                if (on) {
                    node.scrollIntoView({ block: 'nearest' });
                }
            }
        );
        el.productSearch.setAttribute('aria-activedescendant', 'saleResult' + activeIndex);
    }

    function runSearch(query) {
        // Abort the in-flight request: without this, a slow early response can
        // land after a fast later one and repaint the list with stale results.
        if (searchAbort) {
            searchAbort.abort();
        }
        searchAbort = new AbortController();
        el.searchSpinner.hidden = false;

        fetch(CFG.searchUrl + '?q=' + encodeURIComponent(query), {
            signal: searchAbort.signal,
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Search failed (' + response.status + ')');
                }
                return response.json();
            })
            .then(function (data) {
                results = data.results || [];
                activeIndex = results.length ? 0 : -1;
                renderResults(query);

                // A barcode scanner types the full SKU then Enter, faster than any
                // human. If exactly one row came back on an exact SKU, add it.
                var only = results.length === 1 ? results[0] : null;
                if (only && only.sku.toLowerCase() === query.toLowerCase() && only.shop_stock > 0) {
                    addToCart(only);
                }
            })
            .catch(function (error) {
                if (error.name === 'AbortError') {
                    return;
                }
                el.searchResults.innerHTML =
                    '<li class="sale-search__message text-danger">' +
                    'Could not reach the product search. Check your connection and try again.</li>';
                el.searchResults.hidden = false;
            })
            .finally(function () {
                el.searchSpinner.hidden = true;
            });
    }

    // ------------------------------------------------------------------- cart

    function lineSubtotal(line) {
        return line.unitPrice * line.qty;
    }

    function lineTotal(line) {
        return Math.max(0, lineSubtotal(line) - line.discount);
    }

    function cartSubtotal() {
        return cart.reduce(function (sum, line) {
            return sum + lineTotal(line);
        }, 0);
    }

    function addToCart(row) {
        if (row.shop_stock <= 0) {
            showAlert(row.display_name + ' has no stock in the shop and cannot be sold.');
            return;
        }

        var existing = cart.find(function (line) {
            return line.productId === row.id;
        });

        if (existing) {
            if (existing.qty + 1 > existing.stock) {
                showAlert('Only ' + existing.stock + ' of ' + existing.sku + ' are in the shop.');
                return;
            }
            existing.qty += 1;
        } else {
            cart.push({
                productId: row.id,
                sku: row.sku,
                label: row.display_name,
                meta: [row.brand, row.category].filter(Boolean).join(' · '),
                unitPrice: toMinor(row.price),
                qty: 1,
                discount: 0,
                stock: row.shop_stock
            });
        }

        clearAlert();
        render();
        resetSearch();
        el.searchStatus.textContent = row.display_name + ' added to the sale.';
    }

    function resetSearch() {
        el.productSearch.value = '';
        closeResults();
        el.productSearch.focus();
    }

    function findLine(productId) {
        return cart.find(function (line) {
            return line.productId === productId;
        });
    }

    function render() {
        el.cartEmpty.hidden = cart.length > 0;
        el.cartCount.textContent = cart.length + (cart.length === 1 ? ' item' : ' items');

        el.cartBody.innerHTML = cart.map(function (line) {
            var over = line.qty > line.stock;
            return '' +
                '<tr class="sale-cart__row' + (over ? ' is-over-stock' : '') + '" data-id="' + line.productId + '">' +
                    '<td class="ps-3">' +
                        '<div class="fw-medium">' + escapeHtml(line.label) + '</div>' +
                        '<div class="text-muted small">' + escapeHtml(line.sku) +
                            (line.meta ? ' &middot; ' + escapeHtml(line.meta) : '') + '</div>' +
                        (over
                            ? '<div class="text-danger small">Only ' + line.stock + ' in shop</div>'
                            : '') +
                    '</td>' +
                    '<td class="text-end">' +
                        '<input type="number" class="form-control form-control-sm text-end sale-num"' +
                        ' data-field="price" value="' + toMajor(line.unitPrice) + '"' +
                        ' step="0.01" min="0" inputmode="decimal"' +
                        ' aria-label="Unit price for ' + escapeHtml(line.sku) + '">' +
                    '</td>' +
                    '<td>' +
                        '<div class="input-group input-group-sm sale-qty mx-auto">' +
                            '<button type="button" class="btn btn-outline-secondary" data-step="-1"' +
                            ' aria-label="Decrease quantity for ' + escapeHtml(line.sku) + '">&minus;</button>' +
                            '<input type="number" class="form-control sale-num" data-field="qty"' +
                            ' value="' + line.qty + '" min="' + MIN_QTY + '" step="1" inputmode="numeric"' +
                            ' aria-label="Quantity for ' + escapeHtml(line.sku) + '">' +
                            '<button type="button" class="btn btn-outline-secondary" data-step="1"' +
                            ' aria-label="Increase quantity for ' + escapeHtml(line.sku) + '">+</button>' +
                        '</div>' +
                    '</td>' +
                    '<td class="text-end">' +
                        '<input type="number" class="form-control form-control-sm sale-line-discount sale-num"' +
                        ' data-field="discount" value="' + toMajor(line.discount) + '"' +
                        ' step="0.01" min="0" inputmode="decimal"' +
                        ' aria-label="Discount for ' + escapeHtml(line.sku) + '">' +
                    '</td>' +
                    '<td class="text-end fw-medium sale-num">' + fmt(lineTotal(line)) + '</td>' +
                    '<td>' +
                        '<button type="button" class="btn btn-sm btn-ghost-danger" data-remove="1"' +
                        ' aria-label="Remove ' + escapeHtml(line.sku) + ' from the sale">' +
                            '<i class="las la-trash-alt" aria-hidden="true"></i>' +
                        '</button>' +
                    '</td>' +
                '</tr>';
        }).join('');

        renderTotals();
    }

    function renderTotals() {
        var subtotal = cartSubtotal();
        var discount = toMinor(el.orderDiscount.value);

        // Mirrors Sale.calculate_totals(): subtotal - order discount.
        var grand = Math.max(0, subtotal - Math.min(discount, subtotal));
        var paid = toMinor(el.amountPaid.value);
        var diff = paid - grand;

        el.sumSubtotal.textContent = fmt(subtotal);
        el.sumGrand.textContent = fmt(grand);

        if (diff >= 0) {
            el.dueLabel.textContent = 'Change to return';
            el.sumDue.textContent = fmt(diff);
            el.sumDue.className = 'sale-total__value fs-5 text-success';
        } else {
            el.dueLabel.textContent = 'Amount due';
            el.sumDue.textContent = fmt(-diff);
            el.sumDue.className = 'sale-total__value fs-5 text-danger';
        }

        el.btnComplete.disabled = cart.length === 0 || submitting;
    }

    function grandTotal() {
        var subtotal = cartSubtotal();
        return Math.max(0, subtotal - Math.min(toMinor(el.orderDiscount.value), subtotal));
    }

    // -------------------------------------------------------------- checkout

    /**
     * Client-side mirror of the SaleService guards. The server re-checks all of
     * this -- these messages exist so the cashier is not made to wait for a
     * round trip to learn the discount is too big.
     */
    function validate() {
        if (!cart.length) {
            return 'Add at least one product before completing the sale.';
        }

        for (var i = 0; i < cart.length; i++) {
            var line = cart[i];
            if (line.qty > line.stock) {
                return 'Only ' + line.stock + ' of ' + line.sku + ' are in the shop.';
            }
            if (line.discount > lineSubtotal(line)) {
                return 'The discount on ' + line.sku + ' is more than the line total.';
            }
        }

        if (toMinor(el.orderDiscount.value) > cartSubtotal()) {
            return 'The order discount is more than the subtotal.';
        }
        return '';
    }

    function completeSale() {
        // Guarded rather than only disabled: a double Ctrl+Enter can fire twice
        // before the button's disabled state has painted.
        if (submitting) {
            return;
        }

        var problem = validate();
        if (problem) {
            showAlert(problem);
            return;
        }

        submitting = true;
        clearAlert();
        el.btnComplete.disabled = true;
        el.btnComplete.innerHTML =
            '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Saving&hellip;';

        var payload = {
            items: cart.map(function (line) {
                return {
                    product_id: line.productId,
                    quantity: line.qty,
                    unit_price: toMajor(line.unitPrice),
                    discount: toMajor(line.discount)
                };
            }),
            customer_id: customerField ? customerField.value : '',
            sale_date: saleDateField ? saleDateField.value : '',
            notes: notesField ? notesField.value : '',
            discount_amount: toMajor(toMinor(el.orderDiscount.value)),
            payment_method: el.paymentMethod.value,
            payment_amount: toMajor(toMinor(el.amountPaid.value))
        };

        fetch(CFG.checkoutUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(payload)
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (!result.ok || result.data.status !== 'success') {
                    showAlert(result.data.message || 'The sale could not be completed.');
                    return;
                }
                onSaleComplete(result.data);
            })
            .catch(function () {
                showAlert('Could not reach the server. The sale was NOT saved — check your connection and try again.');
            })
            .finally(function () {
                submitting = false;
                el.btnComplete.innerHTML =
                    '<i class="las la-check-circle fs-5 align-middle me-1"></i> Complete Sale';
                renderTotals();
            });
    }

    function onSaleComplete(data) {
        // Clear the cart so the beforeunload warning doesn't fire when navigating away.
        // We do not call render() here so the UI behind the modal doesn't abruptly blank out.
        cart = [];
        lastSaleId = data.sale_id;
        el.successInvoice.textContent = data.invoice_number || ('#' + data.sale_id);
        el.linkViewSale.href = CFG.saleListUrl + data.sale_id + '/';
        successModal.show();
    }

    function startNextSale() {
        cart = [];
        el.orderDiscount.value = '0.00';
        el.amountPaid.value = '0.00';
        if (customerField) {
            setCustomer('');
        }
        if (notesField) {
            notesField.value = '';
        }
        clearAlert();
        render();
        resetSearch();
    }

    function setCustomer(value) {
        if (customerField.tomselect) {
            customerField.tomselect.setValue(value, true);
        } else {
            customerField.value = value;
        }
        loadCustomerMeta(value);
    }

    // -------------------------------------------------------------- customer

    function loadCustomerMeta(customerId) {
        if (!customerId) {
            el.customerMetaBox.hidden = true;
            renderLoyalty(null);
            return;
        }

        fetch(CFG.customerInfoUrl.replace(/0\/$/, customerId + '/'), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('lookup failed');
                }
                return response.json();
            })
            .then(function (data) {
                var due = toMinor(data.total_due);
                el.customerMetaName.textContent = data.name;
                
                var parts = [];
                if (data.phone) {
                    parts.push(escapeHtml(data.phone));
                }
                parts.push(due > 0
                    ? '<span class="text-danger fw-medium">Outstanding due ' + fmt(due) + '</span>'
                    : '<span class="text-success">No outstanding due</span>');
                
                el.customerMetaExtra.innerHTML = parts.join(' &middot; ');
                el.customerMetaBox.hidden = false;
                
                renderLoyalty(data.loyalty);
            })
            .catch(function () {
                el.customerMetaName.textContent = 'Unknown';
                el.customerMetaExtra.textContent = 'Customer details unavailable.';
                el.customerMetaBox.hidden = false;
                renderLoyalty(null);
            });
    }

    /**
     * Loyalty badge. Hidden unless the payload carries a `loyalty` object.
     */
    function renderLoyalty(loyalty) {
        var slot = el.customerLoyalty;
        var box = el.customerLoyaltyBox;
        if (!slot || !box) {
            return;
        }

        var bits = [];
        if (loyalty && loyalty.tier) {
            bits.push('<span class="badge bg-warning-subtle text-warning-emphasis">' +
                '<i class="las la-award" aria-hidden="true"></i> ' +
                escapeHtml(loyalty.tier) + '</span>');
        }
        if (loyalty && loyalty.points) {
            bits.push('<div class="text-muted small mt-1">' + escapeHtml(loyalty.points) +
                ' pts</div>');
        }

        if (!bits.length) {
            box.hidden = true;
            slot.innerHTML = '';
            return;
        }

        slot.innerHTML = bits.join('');
        box.hidden = false;
    }

    function saveNewCustomer() {
        var name = el.newCustomerName.value.trim();
        if (!name) {
            el.newCustomerName.classList.add('is-invalid');
            el.newCustomerName.focus();
            return;
        }
        el.newCustomerName.classList.remove('is-invalid');

        var btn = el.newCustomerSaveBtn;
        btn.disabled = true;

        fetch(CFG.customerCreateUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                name: name,
                phone: el.newCustomerPhone.value.trim(),
                email: el.newCustomerEmail.value.trim(),
                address: el.newCustomerAddress.value.trim()
            })
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (result) {
                if (result.status !== 'success') {
                    showAlert(result.message || 'The customer could not be created.');
                    return;
                }
                var label = result.customer.name +
                    (result.customer.phone ? ' - ' + result.customer.phone : '');

                if (customerField.tomselect) {
                    customerField.tomselect.addOption({ id: result.customer.id, name: result.customer.name, phone: result.customer.phone });
                    customerField.tomselect.refreshOptions(false);
                } else {
                    customerField.add(new Option(label, result.customer.id));
                }
                setCustomer(String(result.customer.id));
                customerModal.hide();
            })
            .catch(function () {
                showAlert('Could not reach the server to create the customer.');
            })
            .finally(function () {
                btn.disabled = false;
            });
    }

    // ---------------------------------------------------------------- events

    // Search input
    el.productSearch.addEventListener('input', function () {
        var query = el.productSearch.value.trim();
        console.log('[SaleCreate] Product search triggered with query:', query);
        clearTimeout(searchTimer);

        if (!query) {
            if (searchAbort) {
                searchAbort.abort();
            }
            closeResults();
            return;
        }

        searchTimer = setTimeout(function () {
            runSearch(query);
        }, SEARCH_DEBOUNCE_MS);
    });

    el.productSearch.addEventListener('keydown', function (event) {
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            setActive(activeIndex + 1);
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            setActive(activeIndex - 1);
        } else if (event.key === 'Enter') {
            event.preventDefault();
            // A scanner may send Enter before the debounce has fired; run now.
            if (!results.length) {
                clearTimeout(searchTimer);
                var pending = el.productSearch.value.trim();
                if (pending) {
                    runSearch(pending);
                }
                return;
            }
            if (activeIndex >= 0) {
                addToCart(results[activeIndex]);
            }
        } else if (event.key === 'Escape') {
            closeResults();
        }
    });

    // Delegated: one listener for the whole list, however many rows it holds.
    el.searchResults.addEventListener('mousedown', function (event) {
        var row = event.target.closest('.sale-result');
        if (!row) {
            return;
        }
        event.preventDefault();   // keep focus in the search box
        addToCart(results[Number(row.dataset.index)]);
    });

    el.searchResults.addEventListener('mousemove', function (event) {
        var row = event.target.closest('.sale-result');
        if (row) {
            setActive(Number(row.dataset.index));
        }
    });

    document.addEventListener('click', function (event) {
        if (!event.target.closest('.sale-search')) {
            closeResults();
        }
    });

    // One delegated listener for every cart control, so rows can be replaced
    // wholesale on render without leaking listeners.
    el.cartBody.addEventListener('click', function (event) {
        var row = event.target.closest('.sale-cart__row');
        if (!row) {
            return;
        }
        var line = findLine(Number(row.dataset.id));
        if (!line) {
            return;
        }

        if (event.target.closest('[data-remove]')) {
            cart = cart.filter(function (other) {
                return other !== line;
            });
            clearAlert();
            render();
            return;
        }

        var stepBtn = event.target.closest('[data-step]');
        if (stepBtn) {
            var next = line.qty + Number(stepBtn.dataset.step);
            if (next < MIN_QTY) {
                return;
            }
            if (next > line.stock) {
                showAlert('Only ' + line.stock + ' of ' + line.sku + ' are in the shop.');
                return;
            }
            line.qty = next;
            clearAlert();
            render();
        }
    });

    el.cartBody.addEventListener('input', function (event) {
        var field = event.target.dataset.field;
        var row = event.target.closest('.sale-cart__row');
        if (!field || !row) {
            return;
        }
        var line = findLine(Number(row.dataset.id));
        if (!line) {
            return;
        }

        if (field === 'qty') {
            var typedQty = parseInt(event.target.value, 10);
            if (!isNaN(typedQty) && typedQty > line.stock) {
                showAlert('Only ' + line.stock + ' of ' + line.sku + ' are in the shop.');
                line.qty = line.stock;
                event.target.value = line.stock;
            } else {
                line.qty = Math.max(MIN_QTY, typedQty || MIN_QTY);
            }
        } else if (field === 'price') {
            line.unitPrice = toMinor(event.target.value);
        } else if (field === 'discount') {
            line.discount = toMinor(event.target.value);
        }

        // Repaint the derived numbers only. A full render() would replace the
        // input the cashier is typing in and drop the caret to the end.
        row.classList.toggle('is-over-stock', line.qty > line.stock);
        row.cells[4].textContent = fmt(lineTotal(line));
        renderTotals();
    });

    // Leaving a cart field is the point at which a half-typed value is settled,
    // so that is when the row is normalised back to canonical form.
    el.cartBody.addEventListener('change', function (event) {
        if (event.target.dataset.field) {
            render();
        }
    });

    [el.orderDiscount, el.amountPaid].forEach(function (input) {
        input.addEventListener('input', renderTotals);
    });

    page.querySelector('.sale-methods').addEventListener('click', function (event) {
        var btn = event.target.closest('[data-method]');
        if (!btn) {
            return;
        }
        el.paymentMethod.value = btn.dataset.method;
        Array.prototype.forEach.call(
            page.querySelectorAll('.sale-methods [data-method]'),
            function (other) {
                var on = other === btn;
                other.classList.toggle('btn-primary', on);
                other.classList.toggle('btn-outline-primary', !on);
                other.setAttribute('aria-checked', on ? 'true' : 'false');
            }
        );
    });

    page.addEventListener('click', function (event) {
        var action = (event.target.closest('[data-sale-action]') || {}).dataset;
        if (!action) {
            return;
        }
        if (action.saleAction === 'pay-exact') {
            el.amountPaid.value = toMajor(grandTotal());
            renderTotals();
        } else if (action.saleAction === 'new-customer') {
            el.newCustomerForm.reset();
            el.newCustomerName.classList.remove('is-invalid');
            customerModal.show();
        }
    });

    el.saleAlert.querySelector('[data-sale-dismiss-alert]').addEventListener('click', clearAlert);
    el.btnComplete.addEventListener('click', completeSale);
    el.newCustomerSaveBtn.addEventListener('click', saveNewCustomer);

    el.btnReset.addEventListener('click', function () {
        if (!cart.length) {
            startNextSale();
        } else {
            if (typeof showDangerModal === 'function') {
                showDangerModal(
                    'Are you sure you want to clear this sale and start over? All unsaved items will be lost.',
                    'Clear Sale',
                    function() {
                        startNextSale();
                    }
                );
            } else if (window.confirm('Clear this sale and start over?')) {
                startNextSale();
            }
        }
    });

    el.btnPrintReceipt.addEventListener('click', function () {
        window.open(CFG.receiptUrl.replace(/0\/print\/$/, lastSaleId + '/print/'), '_blank');
    });

    el.btnNextSale.addEventListener('click', function () {
        successModal.hide();
        startNextSale();
    });

    // The form must never navigate: Enter in any input would otherwise reload
    // the page and silently discard the cart.
    document.getElementById('saleForm').addEventListener('submit', function (event) {
        event.preventDefault();
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'F2') {
            event.preventDefault();
            el.productSearch.focus();
            el.productSearch.select();
        } else if (event.key === 'F4') {
            event.preventDefault();
            el.amountPaid.focus();
            el.amountPaid.select();
        } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            completeSale();
        }
    });

    window.addEventListener('beforeunload', function (event) {
        if (cart.length && !submitting) {
            event.preventDefault();
            event.returnValue = '';
        }
    });

    // ------------------------------------------------------------------ init

    successModal = new bootstrap.Modal(el.saleSuccessModal);
    customerModal = new bootstrap.Modal(el.newCustomerModal);

    if (customerField && customerField.tagName === 'SELECT') {
        console.log('[SaleCreate] Initializing TomSelect on customerField...');
        try {
            new TomSelect(customerField, {
                valueField: 'id',
                labelField: 'name',
                searchField: ['name', 'phone'],
                maxItems: 1,
                closeAfterSelect: true,
                placeholder: 'Search for a customer...',
                allowEmptyOption: true,
                preload: 'focus',
                shouldLoad: function(query) {
                    return true;
                },
                load: function(query, callback) {
                    var url = CFG.customerSearchUrl + '?q=' + encodeURIComponent(query);
                    console.log('[SaleCreate] TomSelect fetching:', url);
                    fetch(url)
                        .then(function(response) {
                            return response.json();
                        })
                        .then(function(json) {
                            console.log('[SaleCreate] TomSelect got results:', json.results);
                            callback(json.results || []);
                        })
                        .catch(function(err) {
                            console.error('[SaleCreate] TomSelect fetch error:', err);
                            callback();
                        });
                },
                render: {
                    option: function(item, escape) {
                        var phone = item.phone ? '<br><small class="text-muted">' + escape(item.phone) + '</small>' : '';
                        return '<div><span class="fw-medium">' + escape(item.name) + '</span>' + phone + '</div>';
                    },
                    item: function(item, escape) {
                        return '<div>' + escape(item.name) + '</div>';
                    }
                },
                onChange: loadCustomerMeta
            });
            console.log('[SaleCreate] TomSelect initialized successfully.');
        } catch (e) {
            console.error('[SaleCreate] TomSelect initialization failed!', e);
        }
    } else {
        console.warn('[SaleCreate] No <select name="customer"> found! TomSelect NOT initialized.');
    }

    render();
    el.productSearch.focus();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSaleCreate);
} else {
    initSaleCreate();
}
