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

from .models import Sale, SaleItem
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
            'items__product', 'items__batch'
        ),
        pk=pk
    )
    
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
    """API endpoint to get product info with available batches."""
    product = get_object_or_404(Product, pk=product_id)
    batches = Batch.objects.filter(
        product=product,
        quantity__gt=0
    ).select_related('warehouse').order_by('purchase_date')
    
    data = {
        'id': product.id,
        'name': product.name,
        'sku': product.sku,
        'default_price': str(product.default_selling_price),
        'total_stock': product.total_stock,
        'batches': [{
            'id': b.id,
            'batch_number': b.batch_number,
            'quantity': b.quantity,
            'buy_price': str(b.buy_price),
            'warehouse': b.warehouse.name,
            'warehouse_id': b.warehouse.id,
            'purchase_date': b.purchase_date.strftime('%Y-%m-%d'),
        } for b in batches]
    }
    
    return JsonResponse(data)
