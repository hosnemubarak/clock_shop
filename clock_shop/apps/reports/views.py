from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F, Q, Avg
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

from apps.inventory.models import Product, Batch, Category
from apps.sales.models import Sale, SaleItem
from apps.customers.models import Customer, Payment
from apps.warehouse.models import Warehouse, StockTransfer


@login_required
def report_dashboard(request):
    """Main reports dashboard with overview."""
    today = timezone.now().date()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    
    context = {
        'today': today,
        'month_start': month_start,
        'year_start': year_start,
    }
    return render(request, 'reports/dashboard.html', context)


@login_required
def sales_report(request):
    """Sales report with date filtering."""
    today = timezone.now().date()
    date_from = request.GET.get('date_from', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))
    group_by = request.GET.get('group_by', 'day')
    
    # Base queryset
    sales = Sale.objects.filter(
        status='completed',
        sale_date__date__gte=date_from,
        sale_date__date__lte=date_to
    )
    
    # Summary stats
    summary = sales.aggregate(
        total_sales=Sum('total_amount'),
        total_cost=Sum('total_cost'),
        total_discount=Sum('discount_amount'),
        count=Count('id'),
    )
    summary['total_profit'] = (summary['total_sales'] or Decimal('0')) - (summary['total_cost'] or Decimal('0'))
    
    # Group by period
    if group_by == 'day':
        trunc_func = TruncDate('sale_date')
    elif group_by == 'week':
        trunc_func = TruncWeek('sale_date')
    else:
        trunc_func = TruncMonth('sale_date')
    
    sales_by_period = sales.annotate(
        period=trunc_func
    ).values('period').annotate(
        total=Sum('total_amount'),
        cost=Sum('total_cost'),
        count=Count('id')
    ).order_by('period')
    
    # Calculate profit for each period
    sales_data = []
    for s in sales_by_period:
        s['profit'] = (s['total'] or Decimal('0')) - (s['cost'] or Decimal('0'))
        sales_data.append(s)
    
    # Top selling products (exclude custom items)
    top_products = SaleItem.objects.filter(
        sale__status='completed',
        sale__sale_date__date__gte=date_from,
        sale__sale_date__date__lte=date_to,
        is_custom=False,
        product__isnull=False
    ).values(
        'product__name', 'product__sku'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('unit_price')),
        total_profit=Sum(F('quantity') * (F('unit_price') - F('cost_price')))
    ).order_by('-total_revenue')[:10]
    
    context = {
        'date_from': date_from,
        'date_to': date_to,
        'group_by': group_by,
        'summary': summary,
        'sales_by_period': sales_data,
        'top_products': top_products,
    }
    return render(request, 'reports/sales_report.html', context)


@login_required
def profit_report(request):
    """Profit analysis report."""
    today = timezone.now().date()
    date_from = request.GET.get('date_from', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))
    
    # Profit by product (exclude custom items)
    profit_by_product = SaleItem.objects.filter(
        sale__status='completed',
        sale__sale_date__date__gte=date_from,
        sale__sale_date__date__lte=date_to,
        is_custom=False,
        product__isnull=False
    ).values(
        'product__name', 'product__sku', 'product__category__name'
    ).annotate(
        quantity_sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('unit_price')),
        cost=Sum(F('quantity') * F('cost_price')),
    ).annotate(
        profit=F('revenue') - F('cost'),
    ).order_by('-profit')
    
    # Calculate margin
    profit_data = []
    for p in profit_by_product:
        if p['revenue'] and p['revenue'] > 0:
            p['margin'] = round((p['profit'] / p['revenue']) * 100, 2)
        else:
            p['margin'] = 0
        profit_data.append(p)
    
    # Profit by category (exclude custom items)
    profit_by_category = SaleItem.objects.filter(
        sale__status='completed',
        sale__sale_date__date__gte=date_from,
        sale__sale_date__date__lte=date_to,
        is_custom=False,
        product__isnull=False
    ).values(
        'product__category__name'
    ).annotate(
        revenue=Sum(F('quantity') * F('unit_price')),
        cost=Sum(F('quantity') * F('cost_price')),
    ).annotate(
        profit=F('revenue') - F('cost'),
    ).order_by('-profit')
    
    # Profit by warehouse (exclude custom items)
    profit_by_warehouse = SaleItem.objects.filter(
        sale__status='completed',
        sale__sale_date__date__gte=date_from,
        sale__sale_date__date__lte=date_to,
        is_custom=False,
        batch__isnull=False
    ).values(
        'batch__warehouse__name'
    ).annotate(
        revenue=Sum(F('quantity') * F('unit_price')),
        cost=Sum(F('quantity') * F('cost_price')),
    ).annotate(
        profit=F('revenue') - F('cost'),
    ).order_by('-profit')
    
    # Total summary (exclude custom items for accurate profit calc)
    totals = SaleItem.objects.filter(
        sale__status='completed',
        sale__sale_date__date__gte=date_from,
        sale__sale_date__date__lte=date_to,
        is_custom=False
    ).aggregate(
        total_revenue=Sum(F('quantity') * F('unit_price')),
        total_cost=Sum(F('quantity') * F('cost_price')),
    )
    totals['total_profit'] = (totals['total_revenue'] or Decimal('0')) - (totals['total_cost'] or Decimal('0'))
    if totals['total_revenue'] and totals['total_revenue'] > 0:
        totals['margin'] = round((totals['total_profit'] / totals['total_revenue']) * 100, 2)
    else:
        totals['margin'] = 0
    
    context = {
        'date_from': date_from,
        'date_to': date_to,
        'profit_by_product': profit_data[:20],
        'profit_by_category': profit_by_category,
        'profit_by_warehouse': profit_by_warehouse,
        'totals': totals,
    }
    return render(request, 'reports/profit_report.html', context)


@login_required
def stock_report(request):
    """Stock/inventory report."""
    warehouse_id = request.GET.get('warehouse')
    category_id = request.GET.get('category')
    stock_filter = request.GET.get('stock_filter', 'all')
    
    # Stock by product
    batches = Batch.objects.filter(quantity__gt=0)
    
    if warehouse_id:
        batches = batches.filter(warehouse_id=warehouse_id)
    
    stock_summary = batches.values(
        'product__id', 'product__name', 'product__sku', 
        'product__category__name', 'product__default_selling_price'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_value=Sum(F('quantity') * F('buy_price')),
        avg_cost=Avg('buy_price'),
    ).order_by('product__name')
    
    if category_id:
        stock_summary = stock_summary.filter(product__category_id=category_id)
    
    # Apply stock filter
    if stock_filter == 'low':
        stock_summary = stock_summary.filter(total_quantity__lte=10)
    elif stock_filter == 'out':
        stock_summary = stock_summary.filter(total_quantity=0)
    
    # Stock by warehouse
    stock_by_warehouse = Batch.objects.filter(
        quantity__gt=0
    ).values(
        'warehouse__name', 'warehouse__code'
    ).annotate(
        total_items=Sum('quantity'),
        total_value=Sum(F('quantity') * F('buy_price')),
    ).order_by('warehouse__name')
    
    # Stock by category
    stock_by_category = Batch.objects.filter(
        quantity__gt=0
    ).values(
        'product__category__name'
    ).annotate(
        total_items=Sum('quantity'),
        total_value=Sum(F('quantity') * F('buy_price')),
    ).order_by('-total_value')
    
    # Low stock alerts
    low_stock = Batch.objects.filter(
        quantity__gt=0,
        quantity__lte=10
    ).select_related('product', 'warehouse').order_by('quantity')[:20]
    
    # Totals
    totals = Batch.objects.filter(quantity__gt=0).aggregate(
        total_items=Sum('quantity'),
        total_value=Sum(F('quantity') * F('buy_price')),
    )
    
    warehouses = Warehouse.objects.filter(is_active=True)
    categories = Category.objects.filter(is_active=True)
    
    context = {
        'stock_summary': stock_summary,
        'stock_by_warehouse': stock_by_warehouse,
        'stock_by_category': stock_by_category,
        'low_stock': low_stock,
        'totals': totals,
        'warehouses': warehouses,
        'categories': categories,
        'selected_warehouse': warehouse_id,
        'selected_category': category_id,
        'stock_filter': stock_filter,
    }
    return render(request, 'reports/stock_report.html', context)


@login_required
def customer_report(request):
    """Customer analysis report."""
    # Customers with dues
    customers_with_dues = Customer.objects.filter(
        total_due__gt=0
    ).order_by('-total_due')
    
    # Top customers by purchases
    top_customers = Customer.objects.filter(
        total_purchases__gt=0
    ).order_by('-total_purchases')[:20]
    
    # Customer summary
    customer_summary = Customer.objects.aggregate(
        total_customers=Count('id'),
        active_customers=Count('id', filter=Q(is_active=True)),
        total_dues=Sum('total_due'),
        total_purchases=Sum('total_purchases'),
    )
    
    # Recent payments
    recent_payments = Payment.objects.select_related(
        'customer', 'received_by'
    ).order_by('-payment_date')[:20]
    
    context = {
        'customers_with_dues': customers_with_dues,
        'top_customers': top_customers,
        'customer_summary': customer_summary,
        'recent_payments': recent_payments,
    }
    return render(request, 'reports/customer_report.html', context)


@login_required
def transfer_report(request):
    """Stock transfer history report."""
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    status = request.GET.get('status')
    
    transfers = StockTransfer.objects.select_related(
        'source_warehouse', 'destination_warehouse', 'created_by'
    ).prefetch_related('items__source_batch__product')
    
    if date_from:
        transfers = transfers.filter(transfer_date__date__gte=date_from)
    if date_to:
        transfers = transfers.filter(transfer_date__date__lte=date_to)
    if status:
        transfers = transfers.filter(status=status)
    
    # Summary
    transfer_summary = transfers.aggregate(
        total_transfers=Count('id'),
        completed=Count('id', filter=Q(status='completed')),
        pending=Count('id', filter=Q(status='pending')),
        cancelled=Count('id', filter=Q(status='cancelled')),
    )
    
    context = {
        'transfers': transfers[:50],
        'transfer_summary': transfer_summary,
        'date_from': date_from,
        'date_to': date_to,
        'selected_status': status,
    }
    return render(request, 'reports/transfer_report.html', context)


@login_required
def dead_stock_report(request):
    """Report on slow-moving/dead stock."""
    days_threshold = int(request.GET.get('days', 90))
    threshold_date = timezone.now().date() - timedelta(days=days_threshold)
    
    # Get batches that haven't been sold recently
    # First, get products that have been sold recently (exclude custom items)
    recently_sold = SaleItem.objects.filter(
        sale__sale_date__date__gte=threshold_date,
        sale__status='completed',
        is_custom=False,
        product__isnull=False
    ).values_list('product_id', flat=True).distinct()
    
    # Batches of products not sold recently
    dead_stock = Batch.objects.filter(
        quantity__gt=0
    ).exclude(
        product_id__in=recently_sold
    ).select_related('product', 'warehouse').order_by('-quantity')
    
    # Calculate total dead stock value
    dead_stock_summary = dead_stock.aggregate(
        total_items=Sum('quantity'),
        total_value=Sum(F('quantity') * F('buy_price')),
        batch_count=Count('id'),
    )
    
    # Slow moving products (sold but low quantity, exclude custom items)
    slow_moving = SaleItem.objects.filter(
        sale__sale_date__date__gte=threshold_date,
        sale__status='completed',
        is_custom=False,
        product__isnull=False
    ).values(
        'product__id', 'product__name', 'product__sku'
    ).annotate(
        quantity_sold=Sum('quantity')
    ).filter(quantity_sold__lte=5).order_by('quantity_sold')
    
    context = {
        'dead_stock': dead_stock[:50],
        'dead_stock_summary': dead_stock_summary,
        'slow_moving': slow_moving[:30],
        'days_threshold': days_threshold,
        'threshold_date': threshold_date,
    }
    return render(request, 'reports/dead_stock_report.html', context)


@login_required
def batch_report(request):
    """Detailed batch analysis report."""
    warehouse_id = request.GET.get('warehouse')
    product_id = request.GET.get('product')
    
    batches = Batch.objects.select_related('product', 'warehouse').all()
    
    if warehouse_id:
        batches = batches.filter(warehouse_id=warehouse_id)
    if product_id:
        batches = batches.filter(product_id=product_id)
    
    # Batch age analysis
    today = timezone.now().date()
    batch_data = []
    for batch in batches.filter(quantity__gt=0)[:100]:
        age_days = (today - batch.purchase_date).days
        batch_data.append({
            'batch': batch,
            'age_days': age_days,
            'value': batch.quantity * batch.buy_price,
        })
    
    # Sort by age
    batch_data.sort(key=lambda x: -x['age_days'])
    
    warehouses = Warehouse.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True)
    
    context = {
        'batch_data': batch_data,
        'warehouses': warehouses,
        'products': products,
        'selected_warehouse': warehouse_id,
        'selected_product': product_id,
    }
    return render(request, 'reports/batch_report.html', context)
