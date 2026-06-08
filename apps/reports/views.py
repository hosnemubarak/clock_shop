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
    
    # Base sale items query
    sale_items = SaleItem.objects.filter(
        sale__status='completed',
        sale__sale_date__date__gte=date_from,
        sale__sale_date__date__lte=date_to
    ).select_related('sale', 'product', 'product__brand', 'batch__warehouse')
    
    if shop_id:
        sale_items = sale_items.filter(
            batch__warehouse_id=shop_id,
            is_custom=False
        )
        
    # Base return items query
    return_items = SaleReturnItem.objects.filter(
        sale_return__sale__status='completed',
        sale_return__return_date__date__gte=date_from,
        sale_return__return_date__date__lte=date_to
    ).select_related('sale_return', 'sale_item', 'sale_item__sale', 'sale_item__product', 'sale_item__product__brand', 'sale_item__batch__warehouse')
    
    if shop_id:
        return_items = return_items.filter(
            sale_item__batch__warehouse_id=shop_id,
            sale_item__is_custom=False
        )

    # Load querysets to lists to avoid duplicate DB hits
    sale_items = list(sale_items)
    return_items = list(return_items)
    
    # Calculate net stats
    total_sales_gross = Decimal('0.00')
    total_cost_gross = Decimal('0.00')
    total_discount = Decimal('0.00')
    sale_ids = set()
    
    # Group by product
    product_map = {}
    
    for item in sale_items:
        sale_ids.add(item.sale_id)
        
        subtotal = item.sale.subtotal
        sale_discount = item.sale.discount_amount
        item_total_price = item.total_price  # qty * unit_price - discount
        
        sale_discount_share = Decimal('0.00')
        if subtotal > 0:
            sale_discount_share = (sale_discount * item_total_price / subtotal).quantize(Decimal('0.01'))
            
        net_rev = item_total_price - sale_discount_share
        cost = item.total_cost
        
        total_sales_gross += net_rev
        total_cost_gross += cost
        total_discount += item.discount + sale_discount_share
        
        # Product grouping (exclude custom items, and ensure product is not null)
        if not item.is_custom and item.product:
            pid = item.product_id
            if pid not in product_map:
                product_map[pid] = {
                    'product__id': pid,
                    'product__sku': item.product.sku,
                    'product__brand__name': item.product.brand.name if item.product.brand else '',
                    'total_quantity': 0,
                    'total_revenue': Decimal('0.00'),
                    'total_cost': Decimal('0.00'),
                }
            product_map[pid]['total_quantity'] += item.quantity
            product_map[pid]['total_revenue'] += net_rev
            product_map[pid]['total_cost'] += cost
            
    returned_sales = Decimal('0.00')
    returned_cost = Decimal('0.00')
    
    for ret_item in return_items:
        qty = ret_item.quantity
        refund = ret_item.refund_total
        cost = Decimal(qty) * ret_item.sale_item.cost_price
        
        returned_sales += refund
        returned_cost += cost
        
        if not ret_item.sale_item.is_custom and ret_item.sale_item.product:
            pid = ret_item.sale_item.product_id
            if pid in product_map:
                product_map[pid]['total_quantity'] -= qty
                product_map[pid]['total_revenue'] -= refund
                product_map[pid]['total_cost'] -= cost
            else:
                product_map[pid] = {
                    'product__id': pid,
                    'product__sku': ret_item.sale_item.product.sku,
                    'product__brand__name': ret_item.sale_item.product.brand.name if ret_item.sale_item.product.brand else '',
                    'total_quantity': -qty,
                    'total_revenue': -refund,
                    'total_cost': -cost,
                }
                
    summary = {
        'total_sales': total_sales_gross - returned_sales,
        'total_cost': total_cost_gross - returned_cost,
        'total_discount': total_discount,
        'total_profit': (total_sales_gross - returned_sales) - (total_cost_gross - returned_cost),
        'count': len(sale_ids),
    }

    # Group by period in Python
    sales_by_period_map = {}
    for item in sale_items:
        sale_date = item.sale.sale_date
        if group_by == 'day':
            period_key = sale_date.date()
        elif group_by == 'week':
            period_key = (sale_date - timedelta(days=sale_date.weekday())).date()
        else: # month
            period_key = sale_date.date().replace(day=1)
            
        subtotal = item.sale.subtotal
        sale_discount = item.sale.discount_amount
        item_total_price = item.total_price
        
        sale_discount_share = Decimal('0.00')
        if subtotal > 0:
            sale_discount_share = (sale_discount * item_total_price / subtotal).quantize(Decimal('0.01'))
            
        net_rev = item_total_price - sale_discount_share
        cost = item.total_cost
        
        if period_key not in sales_by_period_map:
            sales_by_period_map[period_key] = {
                'period': period_key,
                'total': Decimal('0.00'),
                'cost': Decimal('0.00'),
                'count_sales': set()
            }
        sales_by_period_map[period_key]['total'] += net_rev
        sales_by_period_map[period_key]['cost'] += cost
        sales_by_period_map[period_key]['count_sales'].add(item.sale_id)
        
    returns_by_period_map = {}
    for ret_item in return_items:
        ret_date = ret_item.sale_return.return_date
        if group_by == 'day':
            period_key = ret_date.date()
        elif group_by == 'week':
            period_key = (ret_date - timedelta(days=ret_date.weekday())).date()
        else: # month
            period_key = ret_date.date().replace(day=1)
            
        qty = ret_item.quantity
        refund = ret_item.refund_total
        cost = Decimal(qty) * ret_item.sale_item.cost_price
        
        if period_key not in returns_by_period_map:
            returns_by_period_map[period_key] = {
                'total_refund': Decimal('0.00'),
                'total_cost': Decimal('0.00'),
            }
        returns_by_period_map[period_key]['total_refund'] += refund
        returns_by_period_map[period_key]['total_cost'] += cost
        
    sales_data = []
    all_periods = sorted(list(set(list(sales_by_period_map.keys()) + list(returns_by_period_map.keys()))))
    for period in all_periods:
        s = sales_by_period_map.get(period, {
            'period': period,
            'total': Decimal('0.00'),
            'cost': Decimal('0.00'),
            'count_sales': set()
        })
        ret = returns_by_period_map.get(period, {
            'total_refund': Decimal('0.00'),
            'total_cost': Decimal('0.00'),
        })
        
        net_t = s['total'] - ret['total_refund']
        net_c = s['cost'] - ret['total_cost']
        
        sales_data.append({
            'period': period,
            'total': net_t,
            'cost': net_c,
            'profit': net_t - net_c,
            'count': len(s['count_sales'])
        })
        
    # Top Products
    top_products = []
    for p in product_map.values():
        p['total_profit'] = p['total_revenue'] - p['total_cost']
        top_products.append(p)
    top_products.sort(key=lambda x: -x['total_revenue'])
    top_products = top_products[:10]
    
    # Shop-wise sales breakdown (for comparison)
    shop_sales = []
    if not shop_id:  # Only show breakdown when viewing all shops
        shop_map = {}
        for item in sale_items:
            if item.batch and item.batch.warehouse:
                wh = item.batch.warehouse
                if wh.is_shop and wh.is_active:
                    wid = wh.id
                    if wid not in shop_map:
                        shop_map[wid] = {
                            'shop': wh,
                            'total': Decimal('0.00'),
                            'cost': Decimal('0.00'),
                            'count_sales': set()
                        }
                    subtotal = item.sale.subtotal
                    sale_discount = item.sale.discount_amount
                    item_total_price = item.total_price
                    
                    sale_discount_share = Decimal('0.00')
                    if subtotal > 0:
                        sale_discount_share = (sale_discount * item_total_price / subtotal).quantize(Decimal('0.01'))
                        
                    net_rev = item_total_price - sale_discount_share
                    cost = item.total_cost
                    
                    shop_map[wid]['total'] += net_rev
                    shop_map[wid]['cost'] += cost
                    shop_map[wid]['count_sales'].add(item.sale_id)
                    
        for ret_item in return_items:
            if ret_item.sale_item.batch and ret_item.sale_item.batch.warehouse:
                wh = ret_item.sale_item.batch.warehouse
                if wh.is_shop and wh.is_active:
                    wid = wh.id
                    if wid in shop_map:
                        qty = ret_item.quantity
                        refund = ret_item.refund_total
                        cost = Decimal(qty) * ret_item.sale_item.cost_price
                        
                        shop_map[wid]['total'] -= refund
                        shop_map[wid]['cost'] -= cost
                        
        for wid, data in shop_map.items():
            shop_sales.append({
                'shop': data['shop'],
                'total': data['total'],
                'cost': data['cost'],
                'profit': data['total'] - data['cost'],
                'count': len(data['count_sales'])
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
        
    # Fetch sale items and return items matching the period and filters
    sale_items = SaleItem.objects.filter(**base_filter).select_related(
        'sale', 'product', 'product__category', 'product__brand', 'batch__warehouse'
    )
    returned_items = SaleReturnItem.objects.filter(**returns_filter).select_related(
        'sale_return', 'sale_item', 'sale_item__sale', 'sale_item__product', 'sale_item__product__category', 'sale_item__product__brand', 'sale_item__batch__warehouse'
    )
    
    sale_items = list(sale_items)
    returned_items = list(returned_items)
    
    product_data = {}
    category_data_map = {}
    warehouse_data_map = {}
    
    total_revenue = Decimal('0.00')
    total_cost = Decimal('0.00')
    
    for item in sale_items:
        subtotal = item.sale.subtotal
        sale_discount = item.sale.discount_amount
        item_total_price = item.total_price  # (quantity * unit_price) - discount
        
        sale_discount_share = Decimal('0.00')
        if subtotal > 0:
            sale_discount_share = (sale_discount * item_total_price / subtotal).quantize(Decimal('0.01'))
            
        net_rev = item_total_price - sale_discount_share
        cost = item.total_cost
        qty = item.quantity
        
        # Product
        pid = item.product.id
        if pid not in product_data:
            product_data[pid] = {
                'product__id': pid,
                'product__sku': item.product.sku,
                'product__brand__name': item.product.brand.name if item.product.brand else '',
                'product__category__name': item.product.category.name if item.product.category else '',
                'quantity_sold': 0,
                'revenue': Decimal('0.00'),
                'cost': Decimal('0.00'),
            }
        product_data[pid]['quantity_sold'] += qty
        product_data[pid]['revenue'] += net_rev
        product_data[pid]['cost'] += cost
        
        # Category
        if item.product.category:
            cid = item.product.category.id
            if cid not in category_data_map:
                category_data_map[cid] = {
                    'product__category__id': cid,
                    'product__category__name': item.product.category.name,
                    'revenue': Decimal('0.00'),
                    'cost': Decimal('0.00'),
                }
            category_data_map[cid]['revenue'] += net_rev
            category_data_map[cid]['cost'] += cost
            
        # Warehouse
        if item.batch and item.batch.warehouse:
            wid = item.batch.warehouse.id
            if wid not in warehouse_data_map:
                warehouse_data_map[wid] = {
                    'batch__warehouse__id': wid,
                    'batch__warehouse__name': item.batch.warehouse.name,
                    'batch__warehouse__is_shop': item.batch.warehouse.is_shop,
                    'revenue': Decimal('0.00'),
                    'cost': Decimal('0.00'),
                }
            warehouse_data_map[wid]['revenue'] += net_rev
            warehouse_data_map[wid]['cost'] += cost
            
        total_revenue += net_rev
        total_cost += cost
        
    for ret_item in returned_items:
        qty = ret_item.quantity
        refund = ret_item.refund_total
        cost = Decimal(qty) * ret_item.sale_item.cost_price
        
        # Product
        pid = ret_item.sale_item.product_id
        if pid not in product_data:
            product_data[pid] = {
                'product__id': pid,
                'product__sku': ret_item.sale_item.product.sku,
                'product__brand__name': ret_item.sale_item.product.brand.name if ret_item.sale_item.product.brand else '',
                'product__category__name': ret_item.sale_item.product.category.name if ret_item.sale_item.product.category else '',
                'quantity_sold': 0,
                'revenue': Decimal('0.00'),
                'cost': Decimal('0.00'),
            }
        product_data[pid]['quantity_sold'] -= qty
        product_data[pid]['revenue'] -= refund
        product_data[pid]['cost'] -= cost
        
        # Category
        if ret_item.sale_item.product.category:
            cid = ret_item.sale_item.product.category.id
            if cid not in category_data_map:
                category_data_map[cid] = {
                    'product__category__id': cid,
                    'product__category__name': ret_item.sale_item.product.category.name,
                    'revenue': Decimal('0.00'),
                    'cost': Decimal('0.00'),
                }
            category_data_map[cid]['revenue'] -= refund
            category_data_map[cid]['cost'] -= cost
            
        # Warehouse
        if ret_item.sale_item.batch and ret_item.sale_item.batch.warehouse:
            wid = ret_item.sale_item.batch.warehouse.id
            if wid not in warehouse_data_map:
                warehouse_data_map[wid] = {
                    'batch__warehouse__id': wid,
                    'batch__warehouse__name': ret_item.sale_item.batch.warehouse.name,
                    'batch__warehouse__is_shop': ret_item.sale_item.batch.warehouse.is_shop,
                    'revenue': Decimal('0.00'),
                    'cost': Decimal('0.00'),
                }
            warehouse_data_map[wid]['revenue'] -= refund
            warehouse_data_map[wid]['cost'] -= cost
            
        total_revenue -= refund
        total_cost -= cost
        
    # Build final list and calculate margins/profits
    profit_data = []
    for p in product_data.values():
        p['profit'] = p['revenue'] - p['cost']
        if p['revenue'] and p['revenue'] > 0:
            p['margin'] = round((p['profit'] / p['revenue']) * 100, 2)
        else:
            p['margin'] = 0
        profit_data.append(p)
    profit_data.sort(key=lambda x: -x['profit'])
    
    # Paginate profit by product
    paginator = Paginator(profit_data, 20)
    page = request.GET.get('page')
    profit_by_product_page = paginator.get_page(page)
    
    category_data = []
    for c in category_data_map.values():
        c['profit'] = c['revenue'] - c['cost']
        category_data.append(c)
    category_data.sort(key=lambda x: -x['profit'])
    
    warehouse_data = []
    for w in warehouse_data_map.values():
        w['profit'] = w['revenue'] - w['cost']
        warehouse_data.append(w)
    warehouse_data.sort(key=lambda x: -x['profit'])
    
    totals = {
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'total_profit': total_revenue - total_cost,
    }
    if total_revenue and total_revenue > 0:
        totals['margin'] = round((totals['total_profit'] / total_revenue) * 100, 2)
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
