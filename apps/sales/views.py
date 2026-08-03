from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
import json
import logging

from .models import Sale
from .forms import SaleForm, PaymentForm
from apps.inventory.models import Product, ProductStock
from apps.warehouse.models import Warehouse
from apps.customers.models import Customer, Payment
from apps.core.utils import create_audit_log

logger = logging.getLogger(__name__)

# How many products the sale-screen search returns when the caller doesn't say.
PRODUCT_SEARCH_LIMIT = 25


def _to_int_or(value, fallback):
    """Parse a query-string integer, falling back on anything unusable."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


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
    """Render the sale screen.

    GET only. The page never submits this form -- its script posts JSON to
    ``sales:pos_checkout``, which is the single sale-creation path. A POST branch
    used to live here as a second, divergent implementation that nothing could
    reach; it was deleted rather than kept in sync.
    """
    shop = Warehouse.objects.filter(is_shop=True).first()

    if not shop:
        messages.error(request, 'No shop warehouse configured. Please configure a shop warehouse first.')
        return redirect('core:dashboard')

    form = SaleForm(initial={'sale_date': timezone.localdate()})

    context = {
        'form': form,
        # Rendered as the payment-method buttons. Taken from the model rather than
        # hardcoded in the template, which is how an invalid 'mobile_money' option
        # sat in the markup and silently persisted against the reports.
        'payment_methods': Payment.PaymentMethod.choices,
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
def api_product_search(request):
    """Search sellable products for the sale screen.

    Replaces embedding every product in the page as <option> tags, which did not
    scale and could only be searched by SKU. Matches SKU, brand and category, and
    returns shop stock in the same response so adding a line needs no second call.
    """
    query = (request.GET.get('q') or '').strip()

    shop = Warehouse.objects.filter(is_shop=True).first()
    if not shop:
        return JsonResponse({'results': [], 'error': 'No shop warehouse configured.'}, status=409)

    products = Product.objects.filter(is_active=True).select_related('brand', 'category')

    if query:
        products = products.filter(
            Q(sku__icontains=query)
            | Q(brand__name__icontains=query)
            | Q(category__name__icontains=query)
        )

    # Shop stock is what a cashier can actually sell; total_stock includes warehouses.
    products = products.annotate(
        shop_stock=Coalesce(
            Sum('stocks__quantity', filter=Q(stocks__warehouse=shop)),
            Value(0),
        )
    )

    # An exact SKU hit is a barcode scan: surface it first so Enter adds the right line.
    exact_first = Case(
        When(sku__iexact=query, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    ) if query else Value(1, output_field=IntegerField())

    products = products.order_by(exact_first, '-shop_stock', 'sku')

    # Bounded so a blank query cannot serialise the whole catalogue.
    limit = min(_to_int_or(request.GET.get('limit'), PRODUCT_SEARCH_LIMIT), 100)
    rows = list(products[:limit])

    return JsonResponse({
        'results': [{
            'id': p.id,
            'sku': p.sku,
            'brand': p.brand.name if p.brand else '',
            'category': p.category.name if p.category else '',
            'display_name': p.display_name,
            'price': str(p.default_selling_price),
            'shop_stock': p.shop_stock,
            'total_stock': p.total_stock,
        } for p in rows],
        'query': query,
        'truncated': len(rows) == limit,
    })


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
            # The sale screen shows this on the success modal; without it the
            # cashier only ever saw the primary key.
            'invoice_number': sale.invoice_number,
            'message': 'Sale completed successfully.'
        })
        
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    except Exception:
        logger.exception('POS checkout failed')
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)
