from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.core.decorators import staff_or_superuser_required
from django.core.paginator import Paginator
from django.db.models import Sum, Count, F, Q, Avg
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

from apps.inventory.models import Product, Batch, Category
from apps.sales.models import Sale, SaleItem, SaleReturn, SaleReturnItem
from apps.customers.models import Customer, Payment
from apps.warehouse.models import Warehouse, StockTransfer


@staff_or_superuser_required
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


@staff_or_superuser_required
def sales_report(request):
    """Sales report with date and shop filtering."""
    today = timezone.now().date()
    date_from = request.GET.get('date_from', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))
    group_by = request.GET.get('group_by', 'day')
    shop_id = request.GET.get('shop', '')
    
    # Get all shops for filter dropdown
    shops = Warehouse.objects.filter(is_shop=True, is_active=True).order_by('name')
    
    # Base queryset
    sales = Sale.objects.filter(
        status='completed',
        sale_date__date__gte=date_from,
        sale_date__date__lte=date_to
    )
    
    # Filter by shop if selected (based on sale items' batch warehouse)
    if shop_id:
        sales = sales.filter(
            items__batch__warehouse_id=shop_id,
            items__is_custom=False
        ).distinct()
    
    # Summary stats (gross)
    summary = sales.aggregate(
        total_sales=Sum('total_amount'),
        total_cost=Sum('total_cost'),
        total_discount=Sum('discount_amount'),
        count=Count('id'),
    )
    
    # Get returns within the selected date range
    returns = SaleReturn.objects.filter(
        sale__status='completed',
        return_date__date__gte=date_from,
        return_date__date__lte=date_to
    )
    if shop_id:
        returns = returns.filter(
            items__sale_item__batch__warehouse_id=shop_id
        ).distinct()
        
    returns_summary = returns.aggregate(
        total_refund=Sum('refund_amount'),
        total_cost=Sum(F('items__quantity') * F('items__sale_item__cost_price'))
    )
    
    returned_sales = returns_summary['total_refund'] or Decimal('0')
    returned_cost = returns_summary['total_cost'] or Decimal('0')
    
    # Calculate net stats
    summary['total_sales'] = (summary['total_sales'] or Decimal('0')) - returned_sales
    summary['total_cost'] = (summary['total_cost'] or Decimal('0')) - returned_cost
    summary['total_profit'] = summary['total_sales'] - summary['total_cost']
    
    # Group by period
    if group_by == 'day':
        trunc_func = TruncDate('sale_date')
        trunc_func_ret = TruncDate('return_date')
    elif group_by == 'week':
        trunc_func = TruncWeek('sale_date')
        trunc_func_ret = TruncWeek('return_date')
    else:
        trunc_func = TruncMonth('sale_date')
        trunc_func_ret = TruncMonth('return_date')
    
    sales_by_period = sales.annotate(
        period=trunc_func
    ).values('period').annotate(
        total=Sum('total_amount'),
        cost=Sum('total_cost'),
        count=Count('id')
    ).order_by('period')
    
    # Group returns by period
    returns_by_period = returns.annotate(
        period=trunc_func_ret
    ).values('period').annotate(
        total_refund=Sum('refund_amount'),
        total_cost=Sum(F('items__quantity') * F('items__sale_item__cost_price'))
    ).order_by('period')
    
    returns_map = {r['period']: r for r in returns_by_period}
    
    # Calculate profit for each period with returns deducted
    sales_data = []
    for s in sales_by_period:
        period_return = returns_map.get(s['period'], {})
        ret_total = period_return.get('total_refund') or Decimal('0')
        ret_cost = period_return.get('total_cost') or Decimal('0')
        
        s['total'] = (s['total'] or Decimal('0')) - ret_total
        s['cost'] = (s['cost'] or Decimal('0')) - ret_cost
        s['profit'] = s['total'] - s['cost']
        sales_data.append(s)
    
    # Top selling products (exclude custom items)
    top_products_gross = SaleItem.objects.filter(
        sale__status='completed',
        sale__sale_date__date__gte=date_from,
        sale__sale_date__date__lte=date_to,
        is_custom=False,
        product__isnull=False
    )
    if shop_id:
        top_products_gross = top_products_gross.filter(batch__warehouse_id=shop_id)
        
    top_products_agg = top_products_gross.values(
        'product__id', 'product__sku', 'product__brand__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('unit_price')),
        total_cost=Sum(F('quantity') * F('cost_price'))
    )
    
    # Returned products summary
    returned_items_agg = SaleReturnItem.objects.filter(
        sale_return__sale__status='completed',
        sale_return__return_date__date__gte=date_from,
        sale_return__return_date__date__lte=date_to,
        sale_item__is_custom=False
    )
    if shop_id:
        returned_items_agg = returned_items_agg.filter(sale_item__batch__warehouse_id=shop_id)
        
    returned_by_product = returned_items_agg.values('sale_item__product_id').annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('quantity') * (F('sale_item__unit_price') - (F('sale_item__discount') / F('sale_item__quantity')))),
        total_cost=Sum(F('quantity') * F('sale_item__cost_price'))
    )
    
    returns_product_map = {r['sale_item__product_id']: r for r in returned_by_product}
    
    top_products = []
    for p in top_products_agg:
        pid = p['product__id']
        ret = returns_product_map.get(pid, {})
        ret_qty = ret.get('total_quantity') or 0
        ret_rev = ret.get('total_revenue') or Decimal('0')
        ret_cost = ret.get('total_cost') or Decimal('0')
        
        p['total_quantity'] = (p['total_quantity'] or 0) - ret_qty
        p['total_revenue'] = (p['total_revenue'] or Decimal('0')) - ret_rev
        p['total_profit'] = p['total_revenue'] - ((p['total_cost'] or Decimal('0')) - ret_cost)
        top_products.append(p)
        
    # Re-sort by revenue descending and slice to 10
    top_products.sort(key=lambda x: -x['total_revenue'])
    top_products = top_products[:10]
    
    # Shop-wise sales breakdown (for comparison)
    shop_sales = []
    if not shop_id:  # Only show breakdown when viewing all shops
        for shop in shops:
            shop_total = Sale.objects.filter(
                status='completed',
                sale_date__date__gte=date_from,
                sale_date__date__lte=date_to,
                items__batch__warehouse=shop,
                items__is_custom=False
            ).distinct().aggregate(
                total=Sum('total_amount'),
                cost=Sum('total_cost'),
                count=Count('id')
            )
            if shop_total['total']:
                shop_returns = SaleReturn.objects.filter(
                    sale__status='completed',
                    return_date__date__gte=date_from,
                    return_date__date__lte=date_to,
                    items__sale_item__batch__warehouse=shop
                ).distinct().aggregate(
                    total_refund=Sum('refund_amount'),
                    total_cost=Sum(F('items__quantity') * F('items__sale_item__cost_price'))
                )
                ret_refund = shop_returns['total_refund'] or Decimal('0')
                ret_cost = shop_returns['total_cost'] or Decimal('0')
                
                net_total = (shop_total['total'] or Decimal('0')) - ret_refund
                net_cost = (shop_total['cost'] or Decimal('0')) - ret_cost
                
                shop_sales.append({
                    'shop': shop,
                    'total': net_total,
                    'cost': net_cost,
                    'profit': net_total - net_cost,
                    'count': shop_total['count'] or 0
                })
    
    context = {
        'date_from': date_from,
        'date_to': date_to,
        'group_by': group_by,
        'summary': summary,
        'sales_by_period': sales_data,
        'top_products': top_products,
        'shops': shops,
        'selected_shop': shop_id,
        'shop_sales': shop_sales,
        'returned_sales': returned_sales,
    }
    return render(request, 'reports/sales_report.html', context)


@staff_or_superuser_required
def profit_report(request):
    """Profit analysis report with product and shop filters."""
    today = timezone.now().date()
    date_from = request.GET.get('date_from', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))
    product_id = request.GET.get('product', '')
    shop_id = request.GET.get('shop', '')
    category_id = request.GET.get('category', '')
    
    # Get filter options
    from apps.inventory.models import Product, Category
    products = Product.objects.filter(is_active=True).select_related('brand').order_by('sku')
    shops = Warehouse.objects.filter(is_shop=True, is_active=True).order_by('name')
    categories = Category.objects.filter(is_active=True).order_by('name')
    
    # Base filter for all queries
    base_filter = {
        'sale__status': 'completed',
        'sale__sale_date__date__gte': date_from,
        'sale__sale_date__date__lte': date_to,
        'is_custom': False,
        'product__isnull': False,
    }
    
    # Apply product filter
    if product_id:
        base_filter['product_id'] = product_id
    
    # Apply shop filter
    if shop_id:
        base_filter['batch__warehouse_id'] = shop_id
    
    # Apply category filter
    if category_id:
        base_filter['product__category_id'] = category_id
    
    # Profit by product (exclude custom items) - including product ID for mapping returns
    profit_by_product = SaleItem.objects.filter(
        **base_filter
    ).values(
        'product__id', 'product__sku', 'product__brand__name', 'product__category__name'
    ).annotate(
        quantity_sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('unit_price')),
        cost=Sum(F('quantity') * F('cost_price')),
    ).annotate(
        profit=F('revenue') - F('cost'),
    ).order_by('-profit')
    
    # Get returned items matching the period and filters
    returns_filter = {
        'sale_return__sale__status': 'completed',
        'sale_return__return_date__date__gte': date_from,
        'sale_return__return_date__date__lte': date_to,
        'sale_item__is_custom': False,
        'sale_item__product__isnull': False,
    }
    if product_id:
        returns_filter['sale_item__product_id'] = product_id
    if shop_id:
        returns_filter['sale_item__batch__warehouse_id'] = shop_id
    if category_id:
        returns_filter['sale_item__product__category_id'] = category_id
        
    returned_items = SaleReturnItem.objects.filter(**returns_filter)
    
    returned_by_product = returned_items.values('sale_item__product_id').annotate(
        qty=Sum('quantity'),
        refund=Sum(F('quantity') * (F('sale_item__unit_price') - (F('sale_item__discount') / F('sale_item__quantity')))),
        cost=Sum(F('quantity') * F('sale_item__cost_price'))
    )
    returns_prod_map = {r['sale_item__product_id']: r for r in returned_by_product}
    
    # Calculate margin adjusting for returns
    profit_data = []
    for p in profit_by_product:
        pid = p['product__id']
        ret = returns_prod_map.get(pid, {})
        ret_qty = ret.get('qty') or 0
        ret_refund = ret.get('refund') or Decimal('0')
        ret_cost = ret.get('cost') or Decimal('0')
        
        p['quantity_sold'] = (p['quantity_sold'] or 0) - ret_qty
        p['revenue'] = (p['revenue'] or Decimal('0')) - ret_refund
        p['cost'] = (p['cost'] or Decimal('0')) - ret_cost
        p['profit'] = p['revenue'] - p['cost']
        
        if p['revenue'] and p['revenue'] > 0:
            p['margin'] = round((p['profit'] / p['revenue']) * 100, 2)
        else:
            p['margin'] = 0
        profit_data.append(p)
        
    # Re-sort profit data by net profit descending
    profit_data.sort(key=lambda x: -x['profit'])
    
    # Paginate profit by product
    paginator = Paginator(profit_data, 20)
    page = request.GET.get('page')
    profit_by_product_page = paginator.get_page(page)
    
    # Profit by category (exclude custom items)
    profit_by_category = SaleItem.objects.filter(
        **base_filter
    ).values(
        'product__category__id', 'product__category__name'
    ).annotate(
        revenue=Sum(F('quantity') * F('unit_price')),
        cost=Sum(F('quantity') * F('cost_price')),
    ).annotate(
        profit=F('revenue') - F('cost'),
    ).order_by('-profit')
    
    returned_by_cat = returned_items.values('sale_item__product__category_id').annotate(
        refund=Sum(F('quantity') * (F('sale_item__unit_price') - (F('sale_item__discount') / F('sale_item__quantity')))),
        cost=Sum(F('quantity') * F('sale_item__cost_price'))
    )
    returns_cat_map = {r['sale_item__product__category_id']: r for r in returned_by_cat}
    
    category_data = []
    for c in profit_by_category:
        cid = c['product__category__id']
        ret = returns_cat_map.get(cid, {})
        ret_refund = ret.get('refund') or Decimal('0')
        ret_cost = ret.get('cost') or Decimal('0')
        
        c['revenue'] = (c['revenue'] or Decimal('0')) - ret_refund
        c['cost'] = (c['cost'] or Decimal('0')) - ret_cost
        c['profit'] = c['revenue'] - c['cost']
        category_data.append(c)
        
    category_data.sort(key=lambda x: -x['profit'])
    
    # Profit by warehouse/shop (exclude custom items)
    warehouse_filter = base_filter.copy()
    warehouse_filter['batch__isnull'] = False
    if 'product__isnull' in warehouse_filter:
        del warehouse_filter['product__isnull']
    
    profit_by_warehouse = SaleItem.objects.filter(
        **warehouse_filter
    ).values(
        'batch__warehouse__id', 'batch__warehouse__name', 'batch__warehouse__is_shop'
    ).annotate(
        revenue=Sum(F('quantity') * F('unit_price')),
        cost=Sum(F('quantity') * F('cost_price')),
    ).annotate(
        profit=F('revenue') - F('cost'),
    ).order_by('-profit')
    
    returned_by_wh = returned_items.values('sale_item__batch__warehouse__id').annotate(
        refund=Sum(F('quantity') * (F('sale_item__unit_price') - (F('sale_item__discount') / F('sale_item__quantity')))),
        cost=Sum(F('quantity') * F('sale_item__cost_price'))
    )
    returns_wh_map = {r['sale_item__batch__warehouse__id']: r for r in returned_by_wh}
    
    warehouse_data = []
    for w in profit_by_warehouse:
        wid = w['batch__warehouse__id']
        ret = returns_wh_map.get(wid, {})
        ret_refund = ret.get('refund') or Decimal('0')
        ret_cost = ret.get('cost') or Decimal('0')
        
        w['revenue'] = (w['revenue'] or Decimal('0')) - ret_refund
        w['cost'] = (w['cost'] or Decimal('0')) - ret_cost
        w['profit'] = w['revenue'] - w['cost']
        warehouse_data.append(w)
        
    warehouse_data.sort(key=lambda x: -x['profit'])
    
    # Total summary (exclude custom items for accurate profit calc)
    totals = SaleItem.objects.filter(
        **base_filter
    ).aggregate(
        total_revenue=Sum(F('quantity') * F('unit_price')),
        total_cost=Sum(F('quantity') * F('cost_price')),
    )
    
    total_refund_agg = returned_items.aggregate(
        refund=Sum(F('quantity') * (F('sale_item__unit_price') - (F('sale_item__discount') / F('sale_item__quantity')))),
        cost=Sum(F('quantity') * F('sale_item__cost_price'))
    )
    ret_refund_val = total_refund_agg['refund'] or Decimal('0')
    ret_cost_val = total_refund_agg['cost'] or Decimal('0')
    
    totals['total_revenue'] = (totals['total_revenue'] or Decimal('0')) - ret_refund_val
    totals['total_cost'] = (totals['total_cost'] or Decimal('0')) - ret_cost_val
    totals['total_profit'] = totals['total_revenue'] - totals['total_cost']
    if totals['total_revenue'] and totals['total_revenue'] > 0:
        totals['margin'] = round((totals['total_profit'] / totals['total_revenue']) * 100, 2)
    else:
        totals['margin'] = 0
    
    context = {
        'date_from': date_from,
        'date_to': date_to,
        'profit_by_product': profit_by_product_page,
        'profit_by_category': category_data,
        'profit_by_warehouse': warehouse_data,
        'totals': totals,
        'products': products,
        'shops': shops,
        'categories': categories,
        'selected_product': product_id,
        'selected_shop': shop_id,
        'selected_category': category_id,
    }
    return render(request, 'reports/profit_report.html', context)


@staff_or_superuser_required
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
        'product__id', 'product__sku', 'product__brand__name',
        'product__category__name', 'product__default_selling_price'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_value=Sum(F('quantity') * F('buy_price')),
        avg_cost=Avg('buy_price'),
    ).order_by('product__sku')
    
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
    
    # Paginate stock summary
    paginator = Paginator(list(stock_summary), 20)
    page = request.GET.get('page')
    stock_summary_page = paginator.get_page(page)
    
    context = {
        'stock_summary': stock_summary_page,
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


@staff_or_superuser_required
def customer_report(request):
    """Customer analysis report."""
    # Customers with dues
    customers_with_dues = Customer.objects.filter(
        total_due__gt=0
    ).order_by('-total_due')
    
    # Paginate customers with dues
    paginator = Paginator(customers_with_dues, 20)
    page = request.GET.get('page')
    customers_with_dues_page = paginator.get_page(page)
    
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
        'customers_with_dues': customers_with_dues_page,
        'top_customers': top_customers,
        'customer_summary': customer_summary,
        'recent_payments': recent_payments,
    }
    return render(request, 'reports/customer_report.html', context)


@staff_or_superuser_required
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
    
    # Paginate transfers
    paginator = Paginator(transfers, 20)
    page = request.GET.get('page')
    transfers_page = paginator.get_page(page)
    
    context = {
        'transfers': transfers_page,
        'transfer_summary': transfer_summary,
        'date_from': date_from,
        'date_to': date_to,
        'selected_status': status,
    }
    return render(request, 'reports/transfer_report.html', context)


@staff_or_superuser_required
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
        'product__id', 'product__sku', 'product__brand__name'
    ).annotate(
        quantity_sold=Sum('quantity')
    ).filter(quantity_sold__lte=5).order_by('quantity_sold')
    
    # Paginate dead stock
    paginator = Paginator(dead_stock, 20)
    page = request.GET.get('page')
    dead_stock_page = paginator.get_page(page)
    
    context = {
        'dead_stock': dead_stock_page,
        'dead_stock_summary': dead_stock_summary,
        'slow_moving': slow_moving[:30],
        'days_threshold': days_threshold,
        'threshold_date': threshold_date,
    }
    return render(request, 'reports/dead_stock_report.html', context)


@staff_or_superuser_required
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
    
    # Paginate batch data
    paginator = Paginator(batch_data, 20)
    page = request.GET.get('page')
    batch_data_page = paginator.get_page(page)
    
    warehouses = Warehouse.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True)
    
    context = {
        'batch_data': batch_data_page,
        'warehouses': warehouses,
        'products': products,
        'selected_warehouse': warehouse_id,
        'selected_product': product_id,
    }
    return render(request, 'reports/batch_report.html', context)
