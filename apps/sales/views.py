from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from decimal import Decimal
import json
import html
import logging

from .models import Sale, SaleItem
from .forms import SaleForm, SaleItemForm, PaymentForm
from apps.inventory.models import Product, ProductStock
from apps.warehouse.models import Warehouse
from apps.customers.models import Customer, Payment
from apps.core.utils import create_audit_log

logger = logging.getLogger(__name__)


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
        date_from = start_of_month.strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')
    
    paginator = Paginator(sales, 10)
    page = request.GET.get('page')
    sales = paginator.get_page(page)
    
    context = {
        'sales': sales,
        'search': search,
        'status': status,
        'payment_status': payment_status,
        'date_from': date_from,
        'date_to': date_to,
        'date_filter': date_filter,
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

    # Payments are keyed on the sale itself; walk-in sales have no customer but
    # can still carry payments, so do not filter on the customer.
    payments = Payment.objects.filter(sale=sale).order_by('-payment_date')
    
    context = {
        'sale': sale,
        'payments': payments,
    }
    return render(request, 'sales/sale_detail.html', context)


@login_required
def sale_create(request):
    """Create a new sale with manual batch selection."""
    products = Product.objects.filter(is_active=True, total_stock__gt=0)
    customers = Customer.objects.filter(is_active=True)
    shop = Warehouse.objects.filter(is_shop=True).first()
    
    if not shop:
        messages.error(request, 'No shop warehouse configured. Please configure a shop warehouse first.')
        return redirect('core:dashboard')
    
    
    if request.method == 'POST':
        form = SaleForm(request.POST)
        items_data = request.POST.getlist('items')
        
        if form.is_valid() and items_data:
            from apps.sales.services import _to_decimal, _to_int

            # Coerce and validate the whole payload before any write. Previously
            # this happened after sale.save(), so a bad value raised KeyError /
            # InvalidOperation mid-transaction and escaped as an HTTP 500.
            parsed_items = []
            try:
                for index, item_json in enumerate(items_data, start=1):
                    try:
                        item = json.loads(html.unescape(item_json))
                    except ValueError:
                        raise ValueError('Invalid items data format.')
                    if not isinstance(item, dict):
                        raise ValueError(f'Invalid cart item #{index}.')

                    quantity = _to_int(item.get('quantity'), f'quantity for item #{index}')
                    if quantity <= 0:
                        raise ValueError(f'Quantity for item #{index} must be greater than zero.')

                    unit_price = _to_decimal(item.get('unit_price'), f'unit price for item #{index}')
                    if unit_price < 0:
                        raise ValueError(f'Unit price for item #{index} cannot be negative.')

                    discount = _to_decimal(item.get('discount'), f'discount for item #{index}')
                    if discount < 0:
                        raise ValueError(f'Discount for item #{index} cannot be negative.')

                    parsed_items.append({
                        'product_id': _to_int(item.get('product_id'), f'product for item #{index}'),
                        'quantity': quantity,
                        'unit_price': unit_price,
                        'discount': discount,
                    })
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('sales:sale_create')

            sale_items_to_create = []
            try:
                # The ValueErrors below are raised inside the block and caught
                # outside it, so every write -- the Sale row included -- rolls
                # back. The old code deleted the Sale by hand, which could not
                # undo the stock decrements that had already been written.
                with transaction.atomic():
                    sale = form.save(commit=False)
                    sale.created_by = request.user
                    sale.save()

                    total_cost = Decimal('0')
                    subtotal = Decimal('0')

                    # Lock the stock rows in a stable order so two concurrent
                    # sales cannot deadlock against each other.
                    product_ids = sorted({item['product_id'] for item in parsed_items})
                    products_map = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
                    stocks_map = {
                        s.product_id: s
                        for s in ProductStock.objects.select_for_update().filter(
                            product_id__in=product_ids, warehouse=shop
                        ).order_by('product_id')
                    }

                    stocks_to_update = []

                    for item in parsed_items:
                        product = products_map.get(item['product_id'])
                        if not product:
                            raise ValueError(f"Product with ID {item['product_id']} not found.")

                        quantity = item['quantity']
                        stock = stocks_map.get(product.id)

                        # Validate stock
                        if not stock or quantity > stock.quantity:
                            raise ValueError(
                                f'Insufficient stock for {product.display_name} in {shop.name}'
                            )

                        # Create sale item
                        sale_items_to_create.append(SaleItem(
                            sale=sale,
                            product=product,
                            warehouse=shop,
                            quantity=quantity,
                            unit_price=item['unit_price'],
                            cost_price=product.average_cost,
                            discount=item['discount'],
                        ))

                        # Update stock
                        stock.quantity -= quantity
                        stocks_to_update.append(stock)

                    SaleItem.objects.bulk_create(sale_items_to_create)
                    ProductStock.objects.bulk_update(stocks_to_update, ['quantity'])

                    for stock in stocks_to_update:
                        stock.product.update_total_stock()

                    for sale_item in sale_items_to_create:
                        subtotal += sale_item.total_price
                        total_cost += sale_item.total_cost

                    # Update sale totals (mirrors Sale.calculate_totals(): tax is added
                    # after the discount, otherwise the invoice under-charges).
                    sale.subtotal = subtotal
                    sale.total_cost = total_cost
                    sale.total_amount = subtotal - sale.discount_amount + sale.tax_amount
                    sale.save()
                    # Sale post_save signal recalculates the customer balance.
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('sales:sale_create')

            create_audit_log(request, 'SALE', sale, {
                'total': str(sale.total_amount),
                'items': len(sale_items_to_create),
                'customer': sale.customer.name if sale.customer else 'Walk-in'
            })

            messages.success(request, f'Sale "{sale.invoice_number}" created successfully.')
            return redirect('sales:sale_detail', pk=sale.pk)
        else:
            if not items_data:
                messages.error(request, 'Please add at least one item to the sale.')
    else:
        form = SaleForm(initial={'sale_date': timezone.localdate()})
    
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
                
                sale.status = Sale.Status.CANCELLED
                sale.save(update_fields=['status'])
                # Sale post_save signal recalculates the customer balance,
                # which excludes cancelled sales.
                
                create_audit_log(request, 'SALE', sale, {'action': 'cancelled'})
                messages.success(request, f'Sale "{sale.invoice_number}" cancelled.')
    
    return redirect('sales:sale_detail', pk=sale.pk)


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
                    # Create payment record. The Payment post_save signal
                    # recalculates sale.paid_amount, sale.payment_status and the
                    # customer balance from the persisted payment rows.
                    Payment.objects.create(
                        customer=sale.customer,
                        sale=sale,
                        amount=amount,
                        payment_method=form.cleaned_data['payment_method'],
                        reference=form.cleaned_data.get('reference', ''),
                        notes=form.cleaned_data.get('notes', ''),
                        received_by=request.user,
                    )
                    sale.refresh_from_db()

                    create_audit_log(request, 'PAYMENT', sale, {
                        'amount': str(amount),
                        'method': form.cleaned_data['payment_method']
                    })
                    
                    messages.success(request, f'Payment of {amount} recorded.')
        else:
            messages.error(request, 'Invalid payment data.')
    
    return redirect('sales:sale_detail', pk=sale.pk)


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

    try:
        try:
            data = json.loads(request.body)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
            
        from apps.sales.services import SaleService
        sale, payment_amount = SaleService.create_from_pos(data, request.user)
            
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
        
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    except Exception:
        logger.exception('POS checkout failed')
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)
