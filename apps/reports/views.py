from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum, Count, F, Q, Avg
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

from apps.inventory.models import Product, Batch, Category
from apps.sales.models import Sale, SaleItem
from apps.customers.models import Customer, Payment
from apps.warehouse.models import Warehouse, StockTransfer
from .exports import generate_pdf, generate_excel


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
        'product__sku', 'product__brand__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('unit_price')),
        total_profit=Sum(F('quantity') * (F('unit_price') - F('cost_price')))
    ).order_by('-total_revenue')[:10]
    
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
                shop_sales.append({
                    'shop': shop,
                    'total': shop_total['total'] or Decimal('0'),
                    'cost': shop_total['cost'] or Decimal('0'),
                    'profit': (shop_total['total'] or Decimal('0')) - (shop_total['cost'] or Decimal('0')),
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
    }
    
    export = request.GET.get('export')
    if export == 'pdf':
        return generate_pdf('reports/pdf/sales_report.html', context, 'Sales_Report')
    elif export == 'excel':
        headers = ['Period', 'Sales', 'Cost', 'Profit', 'Transactions']
        data = []
        for row in sales_data:
            data.append([
                row['period'].strftime('%Y-%m-%d') if hasattr(row['period'], 'strftime') else row['period'],
                row['total'],
                row['cost'],
                row['profit'],
                row['count']
            ])
            
        filters_dict = {
            'Date From': date_from,
            'Date To': date_to,
            'Group By': group_by.title()
        }
        if shop_id:
            try:
                filters_dict['Shop'] = shops.get(id=shop_id).name
            except Exception:
                pass
                
        totals = [
            'Total',
            summary['total_sales'],
            summary['total_cost'],
            summary['total_profit'],
            summary['count']
        ]
        return generate_excel('Sales_Report', 'Sales Report', filters_dict, headers, data, totals)

    return render(request, 'reports/sales_report.html', context)


@login_required
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
    
    # Profit by product (exclude custom items)
    profit_by_product = SaleItem.objects.filter(
        **base_filter
    ).values(
        'product__sku', 'product__brand__name', 'product__category__name'
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
    
    # Paginate profit by product
    paginator = Paginator(profit_data, 20)
    page = request.GET.get('page')
    profit_by_product_page = paginator.get_page(page)
    
    # Profit by category (exclude custom items)
    profit_by_category = SaleItem.objects.filter(
        **base_filter
    ).values(
        'product__category__name'
    ).annotate(
        revenue=Sum(F('quantity') * F('unit_price')),
        cost=Sum(F('quantity') * F('cost_price')),
    ).annotate(
        profit=F('revenue') - F('cost'),
    ).order_by('-profit')
    
    # Profit by warehouse/shop (exclude custom items)
    warehouse_filter = base_filter.copy()
    warehouse_filter['batch__isnull'] = False
    if 'product__isnull' in warehouse_filter:
        del warehouse_filter['product__isnull']
    
    profit_by_warehouse = SaleItem.objects.filter(
        **warehouse_filter
    ).values(
        'batch__warehouse__name', 'batch__warehouse__is_shop'
    ).annotate(
        revenue=Sum(F('quantity') * F('unit_price')),
        cost=Sum(F('quantity') * F('cost_price')),
    ).annotate(
        profit=F('revenue') - F('cost'),
    ).order_by('-profit')
    
    # Total summary (exclude custom items for accurate profit calc)
    totals = SaleItem.objects.filter(
        **base_filter
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
        'profit_by_product': profit_by_product_page,
        'profit_by_category': profit_by_category,
        'profit_by_warehouse': profit_by_warehouse,
        'totals': totals,
        'products': products,
        'shops': shops,
        'categories': categories,
        'selected_product': product_id,
        'selected_shop': shop_id,
        'selected_category': category_id,
    }
    
    export = request.GET.get('export')
    if export == 'pdf':
        # Pass the full queryset instead of paginated for export
        context['profit_by_product'] = profit_data
        return generate_pdf('reports/pdf/profit_report.html', context, 'Profit_Report')
    elif export == 'excel':
        headers = ['SKU', 'Brand', 'Category', 'Quantity Sold', 'Revenue', 'Cost', 'Profit', 'Margin %']
        data = []
        for row in profit_data:
            data.append([
                row['product__sku'],
                row['product__brand__name'] if row['product__brand__name'] else '-',
                row['product__category__name'] if row['product__category__name'] else '-',
                row['quantity_sold'],
                row['revenue'],
                row['cost'],
                row['profit'],
                row['margin']
            ])
            
        filters_dict = {
            'Date From': date_from,
            'Date To': date_to,
        }
        if product_id:
            try:
                filters_dict['Product'] = products.get(id=product_id).name
            except: pass
        if category_id:
            try:
                filters_dict['Category'] = categories.get(id=category_id).name
            except: pass
        if shop_id:
            try:
                filters_dict['Shop'] = shops.get(id=shop_id).name
            except: pass
                
        totals_row = [
            'Total', '', '', '',
            totals['total_revenue'],
            totals['total_cost'],
            totals['total_profit'],
            totals['margin']
        ]
        return generate_excel('Profit_Report', 'Profit Report', filters_dict, headers, data, totals_row)

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
    
    export = request.GET.get('export')
    if export == 'pdf':
        context['stock_summary'] = stock_summary
        return generate_pdf('reports/pdf/stock_report.html', context, 'Stock_Report')
    elif export == 'excel':
        headers = ['SKU', 'Brand', 'Category', 'Default Price', 'Total Quantity', 'Avg Cost', 'Total Value']
        data = []
        for row in stock_summary:
            data.append([
                row['product__sku'],
                row['product__brand__name'] if row['product__brand__name'] else '-',
                row['product__category__name'] if row['product__category__name'] else '-',
                row['product__default_selling_price'],
                row['total_quantity'],
                row['avg_cost'],
                row['total_value']
            ])
            
        filters_dict = {}
        if warehouse_id:
            try: filters_dict['Warehouse'] = warehouses.get(id=warehouse_id).name
            except: pass
        if category_id:
            try: filters_dict['Category'] = categories.get(id=category_id).name
            except: pass
        filters_dict['Stock Filter'] = stock_filter.title()
                
        totals_row = [
            'Total', '', '', '',
            totals['total_items'],
            '',
            totals['total_value']
        ]
        return generate_excel('Stock_Report', 'Stock Report', filters_dict, headers, data, totals_row)

    return render(request, 'reports/stock_report.html', context)





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
    
    export = request.GET.get('export')
    if export == 'pdf':
        context['transfers'] = transfers
        return generate_pdf('reports/pdf/transfer_report.html', context, 'Transfer_Report')
    elif export == 'excel':
        headers = ['ID', 'Date', 'Source', 'Destination', 'Status', 'Items']
        data = []
        for t in transfers:
            items_str = ", ".join([f"{item.source_batch.product.name} (x{item.quantity})" for item in t.items.all()])
            data.append([
                t.id,
                t.transfer_date.strftime('%Y-%m-%d'),
                t.source_warehouse.name,
                t.destination_warehouse.name,
                t.get_status_display(),
                items_str
            ])
            
        filters_dict = {
            'Date From': date_from,
            'Date To': date_to,
            'Status': status.title() if status else 'All'
        }
        
        totals_row = [
            'Total Transfers:', transfer_summary['total_transfers'],
            'Completed:', transfer_summary['completed'],
            'Pending:', transfer_summary['pending'],
        ]
        return generate_excel('Transfer_Report', 'Transfer Report', filters_dict, headers, data, totals_row)

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
    
    export = request.GET.get('export')
    if export == 'pdf':
        context['dead_stock'] = dead_stock
        return generate_pdf('reports/pdf/dead_stock_report.html', context, 'Dead_Stock_Report')
    elif export == 'excel':
        headers = ['SKU', 'Brand', 'Category', 'Warehouse', 'Quantity', 'Buy Price', 'Total Value']
        data = []
        for batch in dead_stock:
            data.append([
                batch.product.sku,
                batch.product.brand.name if batch.product.brand else '-',
                batch.product.category.name if batch.product.category else '-',
                batch.warehouse.name,
                batch.quantity,
                batch.buy_price,
                batch.quantity * batch.buy_price
            ])
            
        filters_dict = {
            'Inactivity Days': days_threshold,
            'Threshold Date': threshold_date.strftime('%Y-%m-%d')
        }
        
        totals_row = [
            'Total Dead Stock', '', '', '',
            dead_stock_summary['total_items'],
            '',
            dead_stock_summary['total_value']
        ]
        return generate_excel('Dead_Stock_Report', 'Dead Stock Report', filters_dict, headers, data, totals_row)

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
    
    export = request.GET.get('export')
    if export == 'pdf':
        context['batch_data'] = batch_data
        return generate_pdf('reports/pdf/batch_report.html', context, 'Batch_Report')
    elif export == 'excel':
        headers = ['Batch ID', 'Product', 'Warehouse', 'Purchase Date', 'Age (Days)', 'Quantity', 'Buy Price', 'Value']
        data = []
        for item in batch_data:
            b = item['batch']
            data.append([
                b.batch_number,
                b.product.name,
                b.warehouse.name,
                b.purchase_date.strftime('%Y-%m-%d'),
                item['age_days'],
                b.quantity,
                b.buy_price,
                item['value']
            ])
            
        filters_dict = {}
        if warehouse_id:
            try: filters_dict['Warehouse'] = warehouses.get(id=warehouse_id).name
            except: pass
        if product_id:
            try: filters_dict['Product'] = products.get(id=product_id).name
            except: pass
        
        return generate_excel('Batch_Report', 'Batch Report', filters_dict, headers, data)

    return render(request, 'reports/batch_report.html', context)
