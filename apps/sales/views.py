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
import datetime

from .models import Sale, SaleItem
from .forms import SaleForm, SaleItemForm, PaymentForm
from apps.inventory.models import Product, ProductStock
from apps.warehouse.models import Warehouse
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
        sales = sales.filter(sale_date__gte=date_from)
    if date_to:
        sales = sales.filter(sale_date__lte=date_to)
        
    # Date shortcuts
    date_filter = request.GET.get('date_filter')
    if date_filter == 'today':
        today = timezone.localtime().date()
        sales = sales.filter(sale_date=today)
        date_from = today.strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')
    elif date_filter == 'this_month':
        today = timezone.localtime().date()
        start_of_month = today.replace(day=1)
        sales = sales.filter(sale_date__range=(start_of_month, today))
        date_from = start_of_month.date().strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')
    
    paginator = Paginator(sales, 10)
    page = request.GET.get('page')
    sales = paginator.get_page(page)
    
    context = {
        'sales': sales,
        'search': search,
        'payment_status': payment_status,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'sales/sale_list.html', context)


@login_required
def sale_detail(request, pk):
    """View sale/invoice details."""
    sale = get_object_or_404(
        Sale.objects.select_related('customer', 'created_by').prefetch_related(
            'items__product', 'items__warehouse'
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
    shop = Warehouse.objects.filter(is_shop=True).first()
    
    if not shop:
        messages.error(request, 'No shop warehouse configured. Please configure a shop warehouse first.')
        return redirect('dashboard')
    
    
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
                
                # Regular inventory item
                product = Product.objects.get(pk=item['product_id'])
                warehouse = shop
                
                stock = ProductStock.objects.select_for_update().get(product=product, warehouse=warehouse)
                
                # Validate stock
                if quantity > stock.quantity:
                    messages.error(request, f'Insufficient stock for {product.display_name} in {warehouse.name}')
                    sale.delete()
                    return redirect('sale_create')
                
                # Create sale item
                sale_item = SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    warehouse=warehouse,
                    quantity=quantity,
                    unit_price=unit_price,
                    cost_price=product.average_cost,
                    discount=discount,
                )
                
                # Update stock
                stock.quantity -= quantity
                stock.save()
                product.update_total_stock()
                
                subtotal += sale_item.total_price
                total_cost += sale_item.total_cost
            
            # Update sale totals
            sale.subtotal = subtotal
            sale.total_cost = total_cost
            sale.total_amount = subtotal - sale.discount_amount
            sale.save()
            
            # Update customer balance
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
        form = SaleForm(initial={'sale_date': timezone.now().date()})
    
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
                # Restore stock
                for item in sale.items.all():
                    if item.warehouse and item.product:
                        stock, _ = ProductStock.objects.get_or_create(product=item.product, warehouse=item.warehouse, defaults={'quantity': 0})
                        stock.quantity += item.quantity
                        stock.save()
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
                    if sale.customer:
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
            'items__product', 'items__warehouse'
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
    """API endpoint to get product info with available stock from SHOP warehouses only."""
    from apps.warehouse.models import Warehouse
    
    product = get_object_or_404(Product, pk=product_id)
    
    # Only get stocks from shop warehouses (is_shop=True)
    stocks = ProductStock.objects.filter(
        product=product,
        quantity__gt=0,
        warehouse__is_shop=True  # Only shop warehouses
    ).select_related('warehouse').order_by('warehouse__name')
    
    # Get stock breakdown by warehouse (all warehouses for display)
    all_stocks = ProductStock.objects.filter(
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
    } for w in all_stocks]
    
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
        'stocks': [{
            'id': s.id,
            'quantity': s.quantity,
            'average_cost': str(product.average_cost),
            'warehouse': s.warehouse.name,
            'warehouse_id': s.warehouse.id,
            'is_shop': s.warehouse.is_shop,
        } for s in stocks]
    }
    
    return JsonResponse(data)


@login_required
@transaction.atomic
def pos_checkout(request):
    """API endpoint to process a POS checkout."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
        
    import json
    from decimal import Decimal
    from django.utils import timezone
    from apps.sales.models import Sale, SaleItem
    from apps.customers.models import Customer, Payment
    from apps.warehouse.models import Warehouse
    from apps.inventory.models import Product, ProductStock
    from apps.core.utils import create_audit_log
    
    try:
        data = json.loads(request.body)
        
        shop = Warehouse.objects.filter(is_shop=True).first()
        if not shop:
            return JsonResponse({'status': 'error', 'message': 'No shop warehouse configured.'}, status=400)
            
        items = data.get('items', [])
        if not items:
            return JsonResponse({'status': 'error', 'message': 'Cart is empty.'}, status=400)
            
        customer_id = data.get('customer_id')
        discount_amount = Decimal(str(data.get('discount_amount', '0') or '0'))
        payment_amount = Decimal(str(data.get('payment_amount', '0') or '0'))
        payment_method = data.get('payment_method', 'cash')
        
        customer = None
        if customer_id:
            customer = Customer.objects.get(pk=customer_id)
            
        # Create Sale
        from django.utils.dateparse import parse_datetime, parse_date
        sale_date_str = data.get('sale_date')
        if sale_date_str:
            parsed = parse_datetime(sale_date_str) or parse_date(sale_date_str)
            if hasattr(parsed, 'date'):
                sale_date = parsed.date()
            else:
                sale_date = parsed if parsed else timezone.now().date()
        else:
            sale_date = timezone.now().date()
            
        sale = Sale.objects.create(
            customer=customer,
            sale_date=sale_date,
            discount_amount=discount_amount,
            notes=data.get('notes', ''),
            created_by=request.user,
            status='completed' if payment_amount > 0 else 'pending'
        )
        
        subtotal = Decimal('0')
        total_cost = Decimal('0')
        
        for item_data in items:
            product = Product.objects.get(pk=item_data['product_id'])
            quantity = int(item_data['quantity'])
            unit_price = Decimal(str(item_data['unit_price']))
            
            # Stock check
            stock = ProductStock.objects.select_for_update().get(product=product, warehouse=shop)
            if quantity > stock.quantity:
                raise ValueError(f'Insufficient stock for {product.display_name}')
                
            # Create SaleItem
            sale_item = SaleItem.objects.create(
                sale=sale,
                product=product,
                warehouse=shop,
                quantity=quantity,
                unit_price=unit_price,
                cost_price=product.average_cost,
                discount=Decimal('0')
            )
            
            # Update Stock
            stock.quantity -= quantity
            stock.save()
            product.update_total_stock()
            
            subtotal += sale_item.total_price
            total_cost += sale_item.total_cost
            
        # Finalize Sale Totals
        sale.subtotal = subtotal
        sale.total_cost = total_cost
        sale.total_amount = subtotal - discount_amount
        
        # Determine status based on payment
        if payment_amount >= sale.total_amount:
            sale.status = 'paid'
        elif payment_amount > 0:
            sale.status = 'partial'
            
        sale.save()
        
        # Customer Balance
        if customer:
            customer.total_purchases += sale.total_amount
            customer.total_due += sale.total_amount
            customer.save()
            
        # Create Payment
        if payment_amount > 0:
            Payment.objects.create(
                customer=customer,
                sale=sale,
                amount=payment_amount,
                payment_date=timezone.now(),
                payment_method=payment_method,
                reference=f'POS-{sale.invoice_number}',
                received_by=request.user,
                notes='POS Checkout Payment'
            )
            
            if customer:
                customer.total_paid += payment_amount
                customer.total_due -= payment_amount
                customer.save()
                
            sale.paid_amount = payment_amount
            sale.save()
            
        create_audit_log(request, 'SALE', sale, {
            'action': 'pos_checkout',
            'total': str(sale.total_amount),
            'paid': str(payment_amount)
        })
        
        return JsonResponse({
            'status': 'success',
            'sale_id': sale.id,
            'message': 'Sale completed successfully.'
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
