/**
 * quotation-create.js — Quotation creation screen.
 * Simplified version of sale-create.js (no customer, payment, stock validation).
 */
(function () {
  'use strict';

  /* ── DOM references ── */
  const page        = document.getElementById('quotationPage');
  if (!page) return;

  const SEARCH_URL  = page.dataset.searchUrl;
  const SAVE_URL    = page.dataset.saveUrl;
  const LIST_URL    = page.dataset.listUrl;
  const PRINT_URL   = page.dataset.printUrl;
  const DETAIL_URL  = page.dataset.detailUrl;
  const CURRENCY    = page.dataset.currency || '৳';
  const CSRF        = document.querySelector('[name=csrfmiddlewaretoken]').value;

  const $title      = document.getElementById('quotationTitle');
  const $clientName = document.getElementById('clientName');
  const $clientPhone= document.getElementById('clientPhone');
  const $clientAddr = document.getElementById('clientAddress');
  const $date       = document.getElementById('quotationDate');
  const $validUntil = document.getElementById('validUntil');
  const $notes      = document.getElementById('quotationNotes');

  const $search     = document.getElementById('productSearch');
  const $results    = document.getElementById('searchResults');
  const $spinner    = document.getElementById('searchSpinner');
  const $cartBody   = document.getElementById('cartBody');
  const $cartCount  = document.getElementById('cartCount');
  const $cartEmpty  = document.getElementById('cartEmpty');

  const $subtotal   = document.getElementById('sumSubtotal');
  const $discount   = document.getElementById('orderDiscount');
  const $grand      = document.getElementById('sumGrand');

  const $btnSave    = document.getElementById('btnSave');
  const $btnReset   = document.getElementById('btnReset');
  const $btnAddCustom = document.getElementById('btnAddCustom');

  /* ── State ── */
  let cart = [];      // [{id, sku, name, price, qty, discount, isCustom, customDesc}]
  let nextCustomId = -1;
  let searchTimer  = null;

  /* ── Helpers ── */
  const fmt = (n) => CURRENCY + Number(n).toLocaleString('en-IN');

  function recalc() {
    let sub = 0;
    cart.forEach(item => {
      item.total = (item.qty * item.price) - item.discount;
      sub += item.total;
    });
    const disc  = Math.max(0, parseFloat($discount.value) || 0);
    const grand = Math.max(0, sub - disc);

    $subtotal.textContent = fmt(sub);
    $grand.textContent    = fmt(grand);
    $cartCount.textContent = cart.length + ' item' + (cart.length !== 1 ? 's' : '');
    $cartEmpty.hidden      = cart.length > 0;
  }

  /* ── Cart rendering ── */
  function renderCart() {
    $cartBody.innerHTML = '';
    cart.forEach((item, idx) => {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td class="ps-3">
          <span class="fw-medium">${item.isCustom ? item.customDesc : item.name}</span>
          ${!item.isCustom && item.sku ? '<br><small class="text-muted">' + item.sku + '</small>' : ''}
        </td>
        <td class="text-end">
          <input type="number" class="form-control form-control-sm text-end sale-num cart-price"
                 data-idx="${idx}" value="${item.price}" min="0" step="1" style="width:6rem;margin-left:auto;">
        </td>
        <td class="text-center">
          <div class="input-group input-group-sm justify-content-center" style="width:7rem;margin:auto;">
            <button type="button" class="btn btn-light cart-qty-btn" data-idx="${idx}" data-dir="-1">−</button>
            <input type="number" class="form-control text-center sale-num cart-qty"
                   data-idx="${idx}" value="${item.qty}" min="1" style="width:3rem;">
            <button type="button" class="btn btn-light cart-qty-btn" data-idx="${idx}" data-dir="1">+</button>
          </div>
        </td>
        <td class="text-end fw-medium">${fmt(item.total)}</td>
        <td>
          <button type="button" class="btn btn-sm btn-light cart-remove" data-idx="${idx}" title="Remove">
            <i class="las la-times text-danger"></i>
          </button>
        </td>`;
      $cartBody.appendChild(row);
    });
    recalc();
  }

  /* ── Cart event delegation ── */
  $cartBody.addEventListener('input', (e) => {
    const idx = parseInt(e.target.dataset.idx);
    if (isNaN(idx)) return;
    if (e.target.classList.contains('cart-qty')) {
      cart[idx].qty = Math.max(1, parseInt(e.target.value) || 1);
    } else if (e.target.classList.contains('cart-price')) {
      cart[idx].price = Math.max(0, parseFloat(e.target.value) || 0);
    }
    recalc();
    // Update total cell
    const row = e.target.closest('tr');
    if (row) row.querySelector('td:nth-child(4)').textContent = fmt(cart[idx].total);
  });

  $cartBody.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-idx]');
    if (!btn) return;
    const idx = parseInt(btn.dataset.idx);

    if (btn.classList.contains('cart-remove')) {
      cart.splice(idx, 1);
      renderCart();
    } else if (btn.classList.contains('cart-qty-btn')) {
      const dir = parseInt(btn.dataset.dir);
      cart[idx].qty = Math.max(1, cart[idx].qty + dir);
      renderCart();
    }
  });

  $discount.addEventListener('input', recalc);

  /* ── Product search ── */
  $search.addEventListener('input', () => {
    clearTimeout(searchTimer);
    const q = $search.value.trim();
    if (q.length < 1) { $results.hidden = true; return; }
    $spinner.hidden = false;
    searchTimer = setTimeout(() => fetchProducts(q), 250);
  });

  async function fetchProducts(q) {
    try {
      const resp = await fetch(`${SEARCH_URL}?q=${encodeURIComponent(q)}&limit=15`);
      const data = await resp.json();
      $results.innerHTML = '';
      if (data.results.length === 0) {
        $results.innerHTML = '<li class="sale-search__item text-muted p-3">No products found</li>';
      } else {
        data.results.forEach(p => {
          const li = document.createElement('li');
          li.className = 'sale-search__item';
          li.setAttribute('role', 'option');
          li.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
              <div>
                <span class="fw-medium">${p.display_name}</span>
                <br><small class="text-muted">${p.sku} ${p.brand ? '· ' + p.brand : ''}</small>
              </div>
              <span class="badge bg-primary-subtle text-primary">${CURRENCY}${Number(p.price).toLocaleString('en-IN')}</span>
            </div>`;
          li.addEventListener('click', () => addProduct(p));
          $results.appendChild(li);
        });
      }
      $results.hidden = false;
    } catch (err) {
      console.error('Search error', err);
    } finally {
      $spinner.hidden = true;
    }
  }

  function addProduct(p) {
    // Check if already in cart
    const existing = cart.find(c => !c.isCustom && c.id === p.id);
    if (existing) {
      existing.qty += 1;
    } else {
      cart.push({
        id: p.id,
        sku: p.sku,
        name: p.display_name,
        price: parseFloat(p.price) || 0,
        qty: 1,
        discount: 0,
        isCustom: false,
        customDesc: '',
        total: 0,
      });
    }
    $search.value = '';
    $results.hidden = true;
    renderCart();
  }

  // Close results on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.sale-search')) $results.hidden = true;
  });

  /* ── Custom item ── */
  const customModal = new bootstrap.Modal(document.getElementById('customItemModal'));

  $btnAddCustom.addEventListener('click', () => {
    document.getElementById('customDesc').value = '';
    document.getElementById('customPrice').value = '0';
    document.getElementById('customQty').value = '1';
    customModal.show();
  });

  document.getElementById('btnCustomAdd').addEventListener('click', () => {
    const desc  = document.getElementById('customDesc').value.trim();
    const price = parseFloat(document.getElementById('customPrice').value) || 0;
    const qty   = Math.max(1, parseInt(document.getElementById('customQty').value) || 1);

    if (!desc) {
      document.getElementById('customDesc').classList.add('is-invalid');
      return;
    }
    document.getElementById('customDesc').classList.remove('is-invalid');

    cart.push({
      id: nextCustomId--,
      sku: '',
      name: desc,
      price: price,
      qty: qty,
      discount: 0,
      isCustom: true,
      customDesc: desc,
      total: 0,
    });
    customModal.hide();
    renderCart();
  });

  /* ── Save ── */
  $btnSave.addEventListener('click', async () => {
    const title = $title.value.trim();
    if (!title) {
      $title.classList.add('is-invalid');
      $title.focus();
      return;
    }
    $title.classList.remove('is-invalid');

    if (cart.length === 0) {
      alert('Please add at least one item to the quotation.');
      return;
    }

    $btnSave.disabled = true;
    $btnSave.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Saving...';

    const payload = {
      title: title,
      quotation_date: $date.value,
      valid_until: $validUntil.value || null,
      client_name: $clientName.value.trim(),
      client_phone: $clientPhone.value.trim(),
      client_address: $clientAddr.value.trim(),
      discount: parseFloat($discount.value) || 0,
      notes: $notes.value.trim(),
      items: cart.map(item => ({
        product_id: item.isCustom ? null : item.id,
        is_custom: item.isCustom,
        custom_description: item.customDesc,
        quantity: item.qty,
        unit_price: item.price.toString(),
        discount: item.discount.toString(),
      })),
    };

    try {
      const resp = await fetch(SAVE_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': CSRF,
        },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();

      if (data.status === 'success') {
        const qId = data.quotation_id;
        const qNum = data.quotation_number;

        document.getElementById('successNumber').textContent = qNum;
        document.getElementById('btnPrintQuotation').onclick = () => {
          window.open(PRINT_URL.replace('/0/', '/' + qId + '/'), '_blank');
        };
        document.getElementById('btnNewQuotation').onclick = () => location.reload();
        document.getElementById('linkViewQuotation').href = DETAIL_URL.replace('/0/', '/' + qId + '/');

        new bootstrap.Modal(document.getElementById('successModal')).show();
      } else {
        alert(data.message || 'Failed to save quotation.');
      }
    } catch (err) {
      console.error('Save error', err);
      alert('Network error. Please try again.');
    } finally {
      $btnSave.disabled = false;
      $btnSave.innerHTML = '<i class="las la-save fs-5 align-middle me-1"></i> Save Quotation';
    }
  });

  /* ── Reset ── */
  $btnReset.addEventListener('click', () => {
    if (cart.length > 0 && !confirm('Clear all items and start over?')) return;
    cart = [];
    $title.value = '';
    $clientName.value = '';
    $clientPhone.value = '';
    $clientAddr.value = '';
    $validUntil.value = '';
    $discount.value = '0';
    $notes.value = '';
    renderCart();
  });

  /* ── Init ── */
  renderCart();
})();
