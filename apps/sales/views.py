from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F, Count
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from decimal import Decimal
import json
import html

from .models import Sale, SaleItem, SaleReturn, SaleReturnItem
from .forms import SaleForm, SaleItemForm, PaymentForm
from apps.inventory.models import Product, Batch
from apps.customers.models import Customer, Payment
from apps.core.utils import create_audit_log


@login_required
def sale_list(request):
    """List all sales with filtering."""
    sales = Sale.objects.select_related('customer', 'created_by').all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        sales = sales.filter(
            Q(invoice_number__icontains=search) |
            Q(customer__name__icontains=search)
        )
    
    # Status filter
    status = request.GET.get('status')
    if status:
        sales = sales.filter(status=status)
    
    # Payment status filter
    payment_status = request.GET.get('payment_status')
    if payment_status:
        sales = sales.filter(payment_status=payment_status)
    
    # Date filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        sales = sales.filter(sale_date__date__gte=date_from)
    if date_to:
        sales = sales.filter(sale_date__date__lte=date_to)
    
    paginator = Paginator(sales, 10)
    page = request.GET.get('page')
    sales = paginator.get_page(page)
    
    context = {
        'sales': sales,
        'search': search,
    }
    return render(request, 'sales/sale_list.html', context)


@login_required
def sale_detail(request, pk):
    """View sale/invoice details."""
    sale = get_object_or_404(
        Sale.objects.select_related('customer', 'created_by').prefetch_related(
            'items__product', 'items__batch', 'returns__items'
        ),
        pk=pk
    )

    # Cache returned quantities on items to avoid N+1 in the template
    returned_by_item = sale._returned_before()
    any_returnable = False
    for item in sale.items.all():
        item._returned_quantity_cache = returned_by_item.get(item.pk, 0)
        if item.returnable_quantity > 0:
            any_returnable = True

    # Get payments for this sale
    payments = []
    if sale.customer:
        payments = Payment.objects.filter(
            customer=sale.customer,
            sale=sale
        ).order_by('-payment_date')

    context = {
        'sale': sale,
        'payments': payments,
        'any_returnable': any_returnable,
    }
    return render(request, 'sales/sale_detail.html', context)


@login_required
@transaction.atomic
def sale_create(request):
    """Create a new sale with manual batch selection."""
    products = Product.objects.filter(is_active=True, total_stock__gt=0)
    customers = Customer.objects.filter(is_active=True)
    
    if request.method == 'POST':
        form = SaleForm(request.POST)
        items_data = request.POST.getlist('items')
        
        if form.is_valid() and items_data:
            sale = form.save(commit=False)
            sale.created_by = request.user
            sale.save()
            
            total_cost = Decimal('0')
            subtotal = Decimal('0')
            
            for item_json in items_data:
                # Unescape HTML entities before parsing JSON
                item = json.loads(html.unescape(item_json))
                quantity = int(item['quantity'])
                unit_price = Decimal(item['unit_price'])
                discount = Decimal(item.get('discount', '0'))
                is_custom = item.get('is_custom', False)
                
                if is_custom:
                    # Custom item - no product/batch, just description
                    sale_item = SaleItem.objects.create(
                        sale=sale,
                        product=None,
                        batch=None,
                        quantity=quantity,
                        unit_price=unit_price,
                        cost_price=Decimal('0'),  # No cost for custom items
                        discount=discount,
                        custom_description=item.get('product_name', 'Custom Item'),
                        is_custom=True,
                    )
                    subtotal += sale_item.total_price
                else:
                    # Regular inventory item
                    product = Product.objects.get(pk=item['product_id'])
                    batch = Batch.objects.select_for_update().get(pk=item['batch_id'])
                    
                    # Validate batch is from a shop warehouse
                    if not batch.warehouse.is_shop:
                        messages.error(request, f'Product "{product.display_name}" can only be sold from shop locations. Please transfer stock from warehouse to shop first.')
                        sale.delete()
                        return redirect('sale_create')
                    
                    # Validate stock
                    if quantity > batch.quantity:
                        messages.error(request, f'Insufficient stock in batch {batch.batch_number}')
                        sale.delete()
                        return redirect('sale_create')
                    
                    # Create sale item
                    sale_item = SaleItem.objects.create(
                        sale=sale,
                        product=product,
                        batch=batch,
                        quantity=quantity,
                        unit_price=unit_price,
                        cost_price=batch.buy_price,
                        discount=discount,
                    )
                    
                    # Update batch quantity
                    batch.quantity -= quantity
                    batch.save()
                    product.update_total_stock()
                    
                    subtotal += sale_item.total_price
                    total_cost += sale_item.total_cost
            
            # Update sale totals
            sale.subtotal = subtotal
            sale.total_cost = total_cost
            sale.total_amount = subtotal - sale.discount_amount + sale.tax_amount
            sale.save()
            
            # Update customer balance if applicable
            if sale.customer:
                sale.customer.total_purchases += sale.total_amount
                sale.customer.total_due += sale.total_amount
                sale.customer.save()
            
            create_audit_log(request, 'SALE', sale, {
                'total': str(sale.total_amount),
                'items': len(items_data),
                'customer': sale.customer.name if sale.customer else 'Walk-in'
            })
            
            messages.success(request, f'Sale "{sale.invoice_number}" created successfully.')
            return redirect('sale_detail', pk=sale.pk)
        else:
            if not items_data:
                messages.error(request, 'Please add at least one item to the sale.')
    else:
        form = SaleForm(initial={'sale_date': timezone.now()})
    
    context = {
        'form': form,
        'products': products,
        'customers': customers,
    }
    return render(request, 'sales/sale_form.html', context)


@login_required
def sale_cancel(request, pk):
    """Cancel a sale and restore stock."""
    sale = get_object_or_404(Sale, pk=pk)

    if request.method == 'POST':
        with transaction.atomic():
            # Re-fetch inside the lock so a concurrently processed return,
            # payment, or cancel cannot interleave with the stock restore
            sale = Sale.objects.select_for_update().get(pk=pk)

            if sale.status == 'cancelled':
                messages.error(request, 'Sale is already cancelled.')
            elif sale.has_returns:
                messages.error(request, 'Cannot cancel a sale with returns.')
            elif sale.paid_amount > 0:
                messages.error(request, 'Cannot cancel a sale with payments. Process refund first.')
            else:
                # Restore stock to batches (skip custom items)
                for item in sale.items.all():
                    if not item.is_custom and item.batch and item.product:
                        batch = item.batch
                        batch.quantity += item.quantity
                        batch.save()
                        item.product.update_total_stock()

                # Update customer balance
                if sale.customer:
                    sale.customer.total_purchases -= sale.total_amount
                    sale.customer.total_due -= sale.due_amount
                    sale.customer.save()

                sale.status = 'cancelled'
                sale.save()

                create_audit_log(request, 'SALE', sale, {'action': 'cancelled'})
                messages.success(request, f'Sale "{sale.invoice_number}" cancelled.')

    return redirect('sale_detail', pk=sale.pk)


@login_required
def sale_return_create(request, pk):
    """Create a return (full or partial) for a completed sale."""
    sale = get_object_or_404(
        Sale.objects.select_related('customer', 'created_by').prefetch_related(
            'items__product', 'items__batch'
        ),
        pk=pk
    )

    if sale.status != 'completed':
        messages.error(request, 'Returns can only be created for completed sales.')
        return redirect('sale_detail', pk=sale.pk)

    # Build item rows with returned/returnable quantities (single aggregated query)
    returned_by_item = sale._returned_before()
    items = []
    any_returnable = False
    for item in sale.items.all():
        returned = returned_by_item.get(item.pk, 0)
        returnable = item.quantity - returned
        if returnable > 0:
            any_returnable = True
        items.append({
            'item': item,
            'returned': returned,
            'returnable': returnable,
            'entered': '',
        })

    if not any_returnable:
        messages.info(request, 'All items on this invoice have already been fully returned.')
        return redirect('sale_detail', pk=sale.pk)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        notes = request.POST.get('notes', '').strip()
        errors = []

        if not reason:
            errors.append('A reason is required.')

        # Parse requested quantities per item
        return_lines = []
        for entry in items:
            sale_item = entry['item']
            qty_raw = request.POST.get(f'return_qty_{sale_item.pk}', '').strip()
            entry['entered'] = qty_raw
            if not qty_raw:
                continue
            try:
                qty = int(qty_raw)
            except (TypeError, ValueError):
                errors.append(f'Invalid quantity for "{sale_item}".')
                continue
            if qty < 1:
                errors.append(f'Quantity must be at least 1 for "{sale_item}".')
                continue
            if qty > entry['returnable']:
                errors.append(
                    f'Cannot return {qty} of "{sale_item}": '
                    f'only {entry["returnable"]} returnable.'
                )
                continue
            return_lines.append((sale_item, qty))

        if not return_lines:
            errors.append('Select at least one item to return.')

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                with transaction.atomic():
                    sale_return = SaleReturn.objects.create(
                        sale=sale,
                        return_date=timezone.now(),
                        reason=reason,
                        notes=notes,
                        refund_amount=Decimal('0.00'),
                        status='pending',
                        created_by=request.user,
                    )
                    for sale_item, qty in return_lines:
                        SaleReturnItem.objects.create(
                            sale_return=sale_return,
                            sale_item=sale_item,
                            quantity=qty,
                            unit_price=sale_item.unit_price,
                            cost_price=sale_item.cost_price,
                        )
                    sale_return.process_return()

                    create_audit_log(request, 'SALE_RETURN', sale_return, {
                        'invoice': sale.invoice_number,
                        'refund': str(sale_return.refund_amount),
                        'items': len(return_lines),
                    })

                    success_msg = (
                        f'Return "{sale_return.return_number}" processed. '
                        f'Refund: {sale_return.refund_amount}.'
                    )
                    if sale_return.payment_refund_amount > 0:
                        success_msg += (
                            f' Payment refunded to customer: '
                            f'{sale_return.payment_refund_amount}.'
                        )
                    messages.success(request, success_msg)
                    return redirect('sale_return_detail', pk=sale_return.pk)
            except (ValidationError, ValueError) as e:
                messages.error(request, f'Return could not be processed: {e}')

    # Remaining gross value for the live refund preview (same formula as the model)
    remaining_gross = sum(
        (entry['returnable'] * entry['item'].unit_price for entry in items),
        Decimal('0.00'),
    )

    context = {
        'sale': sale,
        'items': items,
        'remaining_gross': remaining_gross,
    }
    return render(request, 'sales/sale_return_form.html', context)


@login_required
def sale_return_list(request):
    """List all sale returns with filtering."""
    returns = SaleReturn.objects.select_related(
        'sale', 'sale__customer', 'created_by'
    ).annotate(
        item_count=Count('items'),
        total_units=Sum('items__quantity'),
    ).order_by('-return_date', '-created_at')

    # Search
    search = request.GET.get('search', '')
    if search:
        returns = returns.filter(
            Q(return_number__icontains=search) |
            Q(sale__invoice_number__icontains=search) |
            Q(sale__customer__name__icontains=search)
        )

    # Status filter
    status = request.GET.get('status')
    if status:
        returns = returns.filter(status=status)

    # Date filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        returns = returns.filter(return_date__date__gte=date_from)
    if date_to:
        returns = returns.filter(return_date__date__lte=date_to)

    # Summary of filtered results (before pagination)
    total_refunds = returns.aggregate(
        total=Sum('refund_amount')
    )['total'] or Decimal('0.00')

    paginator = Paginator(returns, 10)
    page = request.GET.get('page')
    returns = paginator.get_page(page)

    context = {
        'returns': returns,
        'search': search,
        'total_refunds': total_refunds,
    }
    return render(request, 'sales/sale_return_list.html', context)


@login_required
def sale_return_detail(request, pk):
    """View return details."""
    sale_return = get_object_or_404(
        SaleReturn.objects.select_related(
            'sale', 'sale__customer', 'created_by'
        ).prefetch_related('items__sale_item__product', 'items__sale_item__batch'),
        pk=pk
    )
    total_units = sale_return.items.aggregate(total=Sum('quantity'))['total'] or 0
    invoice_reduction = sale_return.refund_amount - sale_return.payment_refund_amount
    context = {
        'sale_return': sale_return,
        'total_units': total_units,
        'invoice_reduction': invoice_reduction,
    }
    return render(request, 'sales/sale_return_detail.html', context)


@login_required
def sale_payment(request, pk):
    """Record payment for a sale."""
    sale = get_object_or_404(Sale, pk=pk)
    
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            
            if amount > sale.due_amount:
                messages.error(request, f'Payment amount exceeds due amount ({sale.due_amount}).')
            else:
                with transaction.atomic():
                    # Create payment record
                    if sale.customer:
                        payment = Payment.objects.create(
                            customer=sale.customer,
                            sale=sale,
                            amount=amount,
                            payment_method=form.cleaned_data['payment_method'],
                            reference=form.cleaned_data.get('reference', ''),
                            notes=form.cleaned_data.get('notes', ''),
                            received_by=request.user,
                        )
                        
                        # Update customer balance
                        sale.customer.total_paid += amount
                        sale.customer.total_due -= amount
                        sale.customer.save()
                    
                    # Update sale
                    sale.paid_amount += amount
                    sale.update_payment_status()
                    
                    create_audit_log(request, 'PAYMENT', sale, {
                        'amount': str(amount),
                        'method': form.cleaned_data['payment_method']
                    })
                    
                    messages.success(request, f'Payment of {amount} recorded.')
        else:
            messages.error(request, 'Invalid payment data.')
    
    return redirect('sale_detail', pk=sale.pk)


@login_required
def sale_print(request, pk):
    """Print-friendly invoice view."""
    sale = get_object_or_404(
        Sale.objects.select_related('customer', 'created_by').prefetch_related(
            'items__product', 'items__batch'
        ),
        pk=pk
    )
    return render(request, 'sales/sale_print.html', {'sale': sale})


@login_required
def pos_view(request):
    """Point of Sale interface."""
    products = Product.objects.filter(is_active=True, total_stock__gt=0).select_related('category')
    customers = Customer.objects.filter(is_active=True)
    
    context = {
        'products': products,
        'customers': customers,
    }
    return render(request, 'sales/pos.html', context)


@login_required
def api_product_info(request, product_id):
    """API endpoint to get product info with available batches from SHOP warehouses only."""
    from apps.warehouse.models import Warehouse
    
    product = get_object_or_404(Product, pk=product_id)
    
    # Only get batches from shop warehouses (is_shop=True)
    batches = Batch.objects.filter(
        product=product,
        quantity__gt=0,
        warehouse__is_shop=True  # Only shop warehouses
    ).select_related('warehouse').order_by('purchase_date')
    
    # Get stock breakdown by warehouse (all warehouses for display)
    all_batches = Batch.objects.filter(
        product=product,
        quantity__gt=0
    ).select_related('warehouse').values(
        'warehouse__id', 'warehouse__name', 'warehouse__is_shop'
    ).annotate(
        total_qty=Sum('quantity')
    ).order_by('-warehouse__is_shop', 'warehouse__name')
    
    warehouse_availability = [{
        'warehouse_id': w['warehouse__id'],
        'warehouse_name': w['warehouse__name'],
        'is_shop': w['warehouse__is_shop'],
        'quantity': w['total_qty']
    } for w in all_batches]
    
    # Check if product has stock in non-shop warehouses (for guidance message)
    warehouse_stock = sum(w['quantity'] for w in warehouse_availability if not w['is_shop'])
    
    # Get shop stock total
    shop_stock = sum(w['quantity'] for w in warehouse_availability if w['is_shop'])
    
    data = {
        'id': product.id,
        'name': product.display_name,
        'sku': product.sku,
        'default_price': str(product.default_selling_price),
        'total_stock': product.total_stock,
        'shop_stock': shop_stock,  # Stock available in shops
        'warehouse_stock': warehouse_stock,  # Stock in non-shop warehouses
        'warehouse_availability': warehouse_availability,  # Detailed breakdown
        'batches': [{
            'id': b.id,
            'batch_number': b.batch_number,
            'quantity': b.quantity,
            'buy_price': str(b.buy_price),
            'warehouse': b.warehouse.name,
            'warehouse_id': b.warehouse.id,
            'is_shop': b.warehouse.is_shop,
            'purchase_date': b.purchase_date.strftime('%Y-%m-%d'),
        } for b in batches]
    }
    
    return JsonResponse(data)
