from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F
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
            'items__product', 'items__batch', 'returns'
        ),
        pk=pk
    )
    
    # Calculate return stats
    returns_total = sum(ret.refund_amount for ret in sale.returns.all())
    net_total = sale.total_amount - returns_total
    
    net_due = Decimal('0.00')
    credit_amount = Decimal('0.00')
    if net_total > sale.paid_amount:
        net_due = net_total - sale.paid_amount
    else:
        credit_amount = sale.paid_amount - net_total
    
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
        'returns_total': returns_total,
        'net_total': net_total,
        'net_due': net_due,
        'credit_amount': credit_amount,
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
            if sale.discount_type == 'percentage':
                sale.discount_amount = (subtotal * (sale.discount_value / Decimal('100.00'))).quantize(Decimal('0.01'))
            else:
                sale.discount_amount = sale.discount_value
            sale.total_amount = subtotal - sale.discount_amount + sale.tax_amount
            sale.save()
            
            # Update customer balance and auto-apply credit if applicable
            if sale.customer:
                # Store credit balance before we recalculate with the new sale
                available_credit = sale.customer.credit_balance
                
                # Check if customer has credit balance to auto-apply
                if available_credit > Decimal('0.00'):
                    credit_to_apply = min(available_credit, sale.due_amount)
                    if credit_to_apply > Decimal('0.00'):
                        Payment.objects.create(
                            customer=sale.customer,
                            sale=sale,
                            amount=credit_to_apply,
                            payment_method='credit_balance',
                            reference='Applied from credit balance',
                            notes=f'Auto-applied credit balance of {credit_to_apply} against invoice {sale.invoice_number}.',
                            received_by=request.user,
                        )
                        # Update sale
                        sale.paid_amount += credit_to_apply
                        sale.update_payment_status()
                
                # Recalculate customer balance to incorporate the new sale and any applied credit payments
                sale.customer.recalculate_balance()
            
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
        if sale.status == 'cancelled':
            messages.error(request, 'Sale is already cancelled.')
        elif sale.paid_amount > 0:
            messages.error(request, 'Cannot cancel a sale with payments. Process refund first.')
        else:
            with transaction.atomic():
                # Restore stock to batches (skip custom items)
                for item in sale.items.all():
                    if not item.is_custom and item.batch and item.product:
                        batch = item.batch
                        batch.quantity += item.quantity
                        batch.save()
                        item.product.update_total_stock()
                
                sale.status = 'cancelled'
                sale.save()
                
                # Update customer balance
                if sale.customer:
                    sale.customer.recalculate_balance()
                
                create_audit_log(request, 'SALE', sale, {'action': 'cancelled'})
                messages.success(request, f'Sale "{sale.invoice_number}" cancelled.')
    
    return redirect('sale_detail', pk=sale.pk)


@login_required
def sale_payment(request, pk):
    """Record payment for a sale."""
    sale = get_object_or_404(Sale, pk=pk)
    
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            payment_method = form.cleaned_data['payment_method']
            
            if payment_method == 'credit_balance':
                if not sale.customer:
                    messages.error(request, "Cannot apply credit balance to a walk-in customer.")
                    return redirect('sale_detail', pk=sale.pk)
                if amount > sale.customer.credit_balance:
                    messages.error(request, f"Insufficient credit balance. Available: {sale.customer.credit_balance}")
                    return redirect('sale_detail', pk=sale.pk)
            
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
                            payment_method=payment_method,
                            reference=form.cleaned_data.get('reference', ''),
                            notes=form.cleaned_data.get('notes', ''),
                            received_by=request.user,
                        )
                        
                        # Recalculate customer balance
                        sale.customer.recalculate_balance()
                    
                    # Recalculate sale
                    sale.recalculate_paid_amount()
                    
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


@login_required
@transaction.atomic
def sale_return_create(request, sale_pk):
    """Process a new return against a completed sale."""
    sale = get_object_or_404(Sale, pk=sale_pk)
    
    # Validation: returns are only allowed for completed sales
    if sale.status != 'completed':
        messages.error(request, "Returns can only be processed for completed sales.")
        return redirect('sale_detail', pk=sale.pk)
        
    if request.method == 'POST':
        # Retrieve form data
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "A reason for the return is required.")
            return redirect('sale_return_create', sale_pk=sale.pk)
            
        # Parse returned quantities
        returned_items_data = []
        total_refund_calculated = Decimal('0.00')
        
        # We loop through items to find returned quantities
        for item in sale.items.all():
            qty_field = f"qty_{item.pk}"
            qty_to_return_str = request.POST.get(qty_field, '0')
            try:
                qty_to_return = int(qty_to_return_str)
            except ValueError:
                qty_to_return = 0
                
            if qty_to_return > 0:
                # Validate against returnable quantity
                max_returnable = item.returnable_quantity
                if qty_to_return > max_returnable:
                    messages.error(request, f"Cannot return more than {max_returnable} units of {item}.")
                    return redirect('sale_return_create', sale_pk=sale.pk)
                    
                # Calculate proportional refund per unit
                # unit_price - (discount / quantity)
                effective_unit_price = item.unit_price - (item.discount / Decimal(item.quantity))
                item_refund = Decimal(qty_to_return) * effective_unit_price
                
                returned_items_data.append((item, qty_to_return, item_refund))
                total_refund_calculated += item_refund
                
        if not returned_items_data:
            messages.error(request, "Please select at least one item to return.")
            return redirect('sale_return_create', sale_pk=sale.pk)
            
        # Create SaleReturn object
        sale_return = SaleReturn.objects.create(
            sale=sale,
            return_date=timezone.now(),
            reason=reason,
            refund_amount=total_refund_calculated,
            created_by=request.user
        )
        
        # Create SaleReturnItems and update stock/batches
        for sale_item, qty, refund in returned_items_data:
            # Create SaleReturnItem
            SaleReturnItem.objects.create(
                sale_return=sale_return,
                sale_item=sale_item,
                quantity=qty
            )
            
            # Restore stock to Batch if not custom
            if not sale_item.is_custom and sale_item.batch:
                batch = sale_item.batch
                # Lock batch for update to avoid race conditions
                batch = Batch.objects.select_for_update().get(pk=batch.pk)
                batch.quantity += qty
                batch.save()
                
                # Update product stock
                if sale_item.product:
                    sale_item.product.update_total_stock()
                    
        # Update customer balance if applicable
        if sale.customer:
            sale.customer.recalculate_balance()
            
        create_audit_log(request, 'RETURN', sale_return, {
            'sale': sale.invoice_number,
            'refund_amount': str(sale_return.refund_amount),
            'items_count': len(returned_items_data)
        })
        
        messages.success(request, f"Return {sale_return.return_number} processed successfully.")
        return redirect('sale_return_detail', pk=sale_return.pk)
        
    # GET request - show form
    # Filter items that can still be returned
    items_with_balance = []
    for item in sale.items.all():
        if item.returnable_quantity > 0:
            effective_unit_price = item.unit_price - (item.discount / Decimal(item.quantity))
            items_with_balance.append({
                'item': item,
                'returnable_qty': item.returnable_quantity,
                'refund_price': effective_unit_price
            })
            
    context = {
        'sale': sale,
        'items_with_balance': items_with_balance,
    }
    return render(request, 'sales/sale_return_form.html', context)


@login_required
def sale_return_list(request):
    """List all returns / credit notes."""
    returns = SaleReturn.objects.select_related('sale', 'created_by').all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        returns = returns.filter(
            Q(return_number__icontains=search) |
            Q(sale__invoice_number__icontains=search) |
            Q(sale__customer__name__icontains=search)
        )
        
    paginator = Paginator(returns, 10)
    page = request.GET.get('page')
    returns = paginator.get_page(page)
    
    context = {
        'returns': returns,
        'search': search,
    }
    return render(request, 'sales/sale_return_list.html', context)


@login_required
def sale_return_detail(request, pk):
    """View details of a specific return / credit note."""
    sale_return = get_object_or_404(
        SaleReturn.objects.select_related('sale__customer', 'created_by').prefetch_related(
            'items__sale_item__product'
        ),
        pk=pk
    )
    
    context = {
        'return': sale_return,
    }
    return render(request, 'sales/sale_return_detail.html', context)


@login_required
def sale_return_print(request, pk):
    """Print credit note."""
    sale_return = get_object_or_404(
        SaleReturn.objects.select_related('sale__customer', 'created_by').prefetch_related(
            'items__sale_item__product'
        ),
        pk=pk
    )
    return render(request, 'sales/sale_return_print.html', {'return': sale_return})
