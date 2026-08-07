from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.core.decorators import manager_required, admin_required
from django.core.paginator import Paginator
from django.db.models import Sum, Count, F, Q, Avg, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce, TruncMonth, TruncWeek
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

from apps.inventory.models import Product, ProductStock, Category
from apps.sales.models import Sale, SaleItem
from apps.customers.models import Customer, Payment
from apps.warehouse.models import Warehouse, StockTransfer
from .exports import handle_export


@manager_required
def report_dashboard(request):
    """Main reports dashboard with overview."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    
    context = {
        'today': today,
        'month_start': month_start,
        'year_start': year_start,
    }
    return render(request, 'reports/dashboard.html', context)


@manager_required
def sales_report(request):
    """Sales report with date and shop filtering."""
    today = timezone.localdate()
    date_from = request.GET.get('date_from', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))
    group_by = request.GET.get('group_by', 'day')
    shop_id = request.GET.get('shop', '')
    
    # Get all shops for filter dropdown
    shops = Warehouse.objects.filter(is_shop=True, is_active=True).order_by('name')
    
    # Base queryset
    sales = Sale.objects.filter(
        status='completed',
        sale_date__gte=date_from,
        sale_date__lte=date_to
    )
    
    # Filter by shop if selected
    if shop_id:
        shop_sale_ids = SaleItem.objects.filter(
            warehouse_id=shop_id,
            is_custom=False
        ).values('sale_id')
        sales = sales.filter(id__in=shop_sale_ids)
    
    # Summary stats
    summary = sales.aggregate(
        total_sales=Sum('total_amount'),
        total_cost=Sum('total_cost'),
        total_discount=Sum('discount_amount'),
        count=Count('id'),
    )
    summary['total_profit'] = (summary['total_sales'] or Decimal('0')) - (summary['total_cost'] or Decimal('0'))
    
    # Group by period. sale_date is a DateField, so 'day' needs no Trunc — just
    # group on the field itself. Week/month still need truncation to snap to boundaries.
    if group_by == 'day':
        sales_by_period = sales.values(
            period=F('sale_date')
        ).annotate(
            total=Sum('total_amount'),
            cost=Sum('total_cost'),
            count=Count('id')
        ).order_by('period')
    else:
        if group_by == 'week':
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
        sale__sale_date__gte=date_from,
        sale__sale_date__lte=date_to,
        is_custom=False,
        product__isnull=False
    ).values(
        'product__id', 'product__sku', 'product__brand__name'
    ).annotate(
        quantity_sold=Sum(F('quantity') - F('returned_quantity')),
        total_revenue=Sum(
            ExpressionWrapper(
                ((F('unit_price') * F('quantity') - F('discount')) * (F('quantity') - F('returned_quantity'))) / F('quantity'),
                output_field=DecimalField()
            )
        ),
        total_profit=Sum(
            ExpressionWrapper(
                (((F('unit_price') * F('quantity') - F('discount')) * (F('quantity') - F('returned_quantity'))) / F('quantity')) - (F('cost_price') * (F('quantity') - F('returned_quantity'))),
                output_field=DecimalField()
            )
        )
    ).order_by('-total_revenue')[:10]
    
    # Shop-wise sales breakdown (for comparison)
    shop_sales = []
    if not shop_id:  # Only show breakdown when viewing all shops
        for shop in shops:
            shop_sale_ids = SaleItem.objects.filter(
                warehouse=shop,
                is_custom=False
            ).values('sale_id')
            
            shop_total = Sale.objects.filter(
                id__in=shop_sale_ids,
                status='completed',
                sale_date__gte=date_from,
                sale_date__lte=date_to
            ).aggregate(
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
    
    top_products_list = list(top_products)
    for p in top_products_list:
        if p['total_revenue'] and p['total_revenue'] > 0:
            p['margin'] = round((p['total_profit'] / p['total_revenue']) * 100, 2)
        else:
            p['margin'] = 0
            
    context = {
        'date_from': date_from,
        'date_to': date_to,
        'group_by': group_by,
        'summary': summary,
        'sales_by_period': sales_data,
        'top_products': top_products_list,
        'shops': shops,
        'selected_shop': shop_id,
        'shop_sales': shop_sales,
    }
    
    context['sales_by_period_export'] = sales_data[:10000]  # Used by PDF template

    def get_excel_data():
        return [
            [
                row['period'].strftime('%Y-%m-%d') if hasattr(row['period'], 'strftime') else row['period'],
                row['total'],
                row['cost'],
                row['profit'],
                row['count']
            ] for row in sales_data[:10000]
        ]

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

    export_response = handle_export(
        request=request,
        context=context,
        filename='Sales_Report',
        pdf_template='reports/pdf/sales_report.html',
        excel_title='Sales Report',
        filters_dict=filters_dict,
        headers=['Period', 'Sales', 'Cost', 'Profit', 'Transactions'],
        data_func=get_excel_data,
        totals=totals
    )
    if export_response:
        return export_response

    return render(request, 'reports/sales_report.html', context)


@manager_required
def profit_report(request):
    """Profit analysis report with product and shop filters."""
    today = timezone.localdate()
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
        'sale__sale_date__gte': date_from,
        'sale__sale_date__lte': date_to,
        'is_custom': False,
        'product__isnull': False,
    }
    
    # Apply product filter
    if product_id:
        base_filter['product_id'] = product_id
    
    # Apply shop filter
    if shop_id:
        base_filter['warehouse_id'] = shop_id
    
    # Apply category filter
    if category_id:
        base_filter['product__category_id'] = category_id
    
    # Profit by product (exclude custom items)
    profit_by_product = SaleItem.objects.filter(
        **base_filter
    ).values(
        'product__sku', 'product__brand__name', 'product__category__name'
    ).annotate(
        quantity_sold=Sum(F('quantity') - F('returned_quantity')),
        revenue=Sum(
            ExpressionWrapper(
                ((F('unit_price') * F('quantity') - F('discount')) * (F('quantity') - F('returned_quantity'))) / F('quantity'),
                output_field=DecimalField()
            )
        ),
        cost=Sum((F('quantity') - F('returned_quantity')) * F('cost_price')),
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
    paginator = Paginator(profit_data, 25)
    page = request.GET.get('page')
    profit_by_product_page = paginator.get_page(page)
    
    # Profit by category (exclude custom items)
    profit_by_category = SaleItem.objects.filter(
        **base_filter
    ).values(
        'product__category__name'
    ).annotate(
        revenue=Sum(
            ExpressionWrapper(
                ((F('unit_price') * F('quantity') - F('discount')) * (F('quantity') - F('returned_quantity'))) / F('quantity'),
                output_field=DecimalField()
            )
        ),
        cost=Sum((F('quantity') - F('returned_quantity')) * F('cost_price')),
    ).annotate(
        profit=F('revenue') - F('cost'),
    ).order_by('-profit')
    
    # Profit by warehouse/shop (exclude custom items)
    warehouse_filter = base_filter.copy()
    warehouse_filter['warehouse__isnull'] = False
    if 'product__isnull' in warehouse_filter:
        del warehouse_filter['product__isnull']
    
    profit_by_warehouse = SaleItem.objects.filter(
        **warehouse_filter
    ).values(
        'warehouse__name', 'warehouse__is_shop'
    ).annotate(
        revenue=Sum(
            ExpressionWrapper(
                ((F('unit_price') * F('quantity') - F('discount')) * (F('quantity') - F('returned_quantity'))) / F('quantity'),
                output_field=DecimalField()
            )
        ),
        cost=Sum((F('quantity') - F('returned_quantity')) * F('cost_price')),
    ).annotate(
        profit=F('revenue') - F('cost'),
    ).order_by('-profit')
    
    # Total summary (exclude custom items for accurate profit calc)
    totals = SaleItem.objects.filter(
        **base_filter
    ).aggregate(
        total_revenue=Sum(
            ExpressionWrapper(
                ((F('unit_price') * F('quantity') - F('discount')) * (F('quantity') - F('returned_quantity'))) / F('quantity'),
                output_field=DecimalField()
            )
        ),
        total_cost=Sum((F('quantity') - F('returned_quantity')) * F('cost_price')),
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
    if export:
        pdf_context = {**context, 'profit_by_product': profit_data}

        def get_excel_data():
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
            return data

        filters_dict = {
            'Date From': date_from,
            'Date To': date_to,
        }
        if product_id:
            try:
                filters_dict['Product'] = products.get(id=product_id).name
            except Exception:
                pass
        if category_id:
            try:
                filters_dict['Category'] = categories.get(id=category_id).name
            except Exception:
                pass
        if shop_id:
            try:
                filters_dict['Shop'] = shops.get(id=shop_id).name
            except Exception:
                pass

        totals_row = [
            'Total', '', '', '',
            totals['total_revenue'],
            totals['total_cost'],
            totals['total_profit'],
            totals['margin']
        ]
        export_response = handle_export(
            request=request,
            context=pdf_context,
            filename='Profit_Report',
            pdf_template='reports/pdf/profit_report.html',
            excel_title='Profit Report',
            filters_dict=filters_dict,
            headers=['SKU', 'Brand', 'Category', 'Quantity Sold', 'Revenue', 'Cost', 'Profit', 'Margin %'],
            data_func=get_excel_data,
            totals=totals_row
        )
        if export_response:
            return export_response

    return render(request, 'reports/profit_report.html', context)


@manager_required
def stock_report(request):
    """Stock/inventory report."""
    warehouse_id = request.GET.get('warehouse')
    category_id = request.GET.get('category')
    stock_filter = request.GET.get('stock_filter', 'all')
    
    # Stock by product
    stocks = ProductStock.objects.filter(quantity__gt=0)
    
    if warehouse_id:
        stocks = stocks.filter(warehouse_id=warehouse_id)
    
    stock_summary = stocks.values(
        'product__id', 'product__sku', 'product__brand__name',
        'product__category__name', 'product__default_selling_price'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_value=Sum(F('quantity') * F('product__average_cost')),
        avg_cost=Avg('product__average_cost'),
    ).order_by('product__sku')
    
    if category_id:
        stock_summary = stock_summary.filter(product__category_id=category_id)
    
    # Apply stock filter
    if stock_filter == 'low':
        from apps.core.models import SystemSettings
        threshold = SystemSettings.get_settings().low_stock_threshold or 5
        stock_summary = stock_summary.filter(total_quantity__lte=threshold)
    elif stock_filter == 'out':
        # The ProductStock base above excludes every zero row, so a
        # total_quantity=0 predicate on it can never match. Out-of-stock has to
        # be derived from Product instead, so products whose stock rows sum to
        # zero AND products with no stock row at all are both reported.
        out_products = Product.objects.filter(is_active=True).select_related(
            'brand', 'category'
        )
        if category_id:
            out_products = out_products.filter(category_id=category_id)

        quantity_filter = Q(stocks__warehouse_id=warehouse_id) if warehouse_id else Q()
        out_products = out_products.annotate(
            on_hand=Coalesce(Sum('stocks__quantity', filter=quantity_filter), 0)
        ).filter(on_hand=0).order_by('sku')

        # Same keys as the values()/annotate() rows above so the paginator, the
        # PDF template and the Excel export keep working unchanged.
        stock_summary = [{
            'product__id': p.id,
            'product__sku': p.sku,
            'product__brand__name': p.brand.name if p.brand else None,
            'product__category__name': p.category.name if p.category else None,
            'product__default_selling_price': p.default_selling_price,
            'total_quantity': 0,
            'total_value': Decimal('0.00'),
            'avg_cost': p.average_cost,
        } for p in out_products]
    
    # Stock by warehouse
    stock_by_warehouse = ProductStock.objects.filter(
        quantity__gt=0
    ).values(
        'warehouse__name', 'warehouse__code'
    ).annotate(
        total_items=Sum('quantity'),
        total_value=Sum(F('quantity') * F('product__average_cost')),
    ).order_by('warehouse__name')
    
    # Stock by category
    stock_by_category = ProductStock.objects.filter(
        quantity__gt=0
    ).values(
        'product__category__name'
    ).annotate(
        total_items=Sum('quantity'),
        total_value=Sum(F('quantity') * F('product__average_cost')),
    ).order_by('-total_value')
    
    # Low stock alerts
    from apps.core.models import SystemSettings
    threshold = SystemSettings.get_settings().low_stock_threshold or 5
    low_stock = ProductStock.objects.filter(
        quantity__gt=0,
        quantity__lte=threshold
    ).select_related('product', 'warehouse').order_by('quantity')[:20]
    
    # Totals
    totals = ProductStock.objects.filter(quantity__gt=0).aggregate(
        total_items=Sum('quantity'),
        total_value=Sum(F('quantity') * F('product__average_cost')),
    )
    
    warehouses = Warehouse.objects.filter(is_active=True)
    categories = Category.objects.filter(is_active=True)
    
    # Paginate stock summary
    paginator = Paginator(list(stock_summary), 25)
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
    if export:
        pdf_context = {**context, 'stock_summary': stock_summary}

        def get_excel_data():
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
            return data

        filters_dict = {}
        if warehouse_id:
            try:
                filters_dict['Warehouse'] = warehouses.get(id=warehouse_id).name
            except Exception:
                pass
        if category_id:
            try:
                filters_dict['Category'] = categories.get(id=category_id).name
            except Exception:
                pass
        filters_dict['Stock Filter'] = stock_filter.title()

        totals_row = [
            'Total', '', '', '',
            totals['total_items'],
            '',
            totals['total_value']
        ]
        export_response = handle_export(
            request=request,
            context=pdf_context,
            filename='Stock_Report',
            pdf_template='reports/pdf/stock_report.html',
            excel_title='Stock Report',
            filters_dict=filters_dict,
            headers=['SKU', 'Brand', 'Category', 'Default Price', 'Total Quantity', 'Avg Cost', 'Total Value'],
            data_func=get_excel_data,
            totals=totals_row
        )
        if export_response:
            return export_response

    return render(request, 'reports/stock_report.html', context)





@manager_required
def transfer_report(request):
    """Stock transfer history report."""
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    status = request.GET.get('status')
    
    transfers = StockTransfer.objects.select_related(
        'source_warehouse', 'destination_warehouse', 'created_by'
    ).prefetch_related('items__product')
    
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
    paginator = Paginator(transfers, 25)
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
    if export:
        pdf_context = {**context, 'transfers': transfers}

        def get_excel_data():
            data = []
            for t in transfers:
                items_str = ", ".join([f"{item.product.display_name} (x{item.quantity})" for item in t.items.all()])
                data.append([
                    t.id,
                    t.transfer_date.strftime('%Y-%m-%d'),
                    t.source_warehouse.name,
                    t.destination_warehouse.name,
                    t.get_status_display(),
                    items_str
                ])
            return data

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
        export_response = handle_export(
            request=request,
            context=pdf_context,
            filename='Transfer_Report',
            pdf_template='reports/pdf/transfer_report.html',
            excel_title='Transfer Report',
            filters_dict=filters_dict,
            headers=['ID', 'Date', 'Source', 'Destination', 'Status', 'Items'],
            data_func=get_excel_data,
            totals=totals_row
        )
        if export_response:
            return export_response

    return render(request, 'reports/transfer_report.html', context)


@manager_required
def dead_stock_report(request):
    """Report on slow-moving/dead stock."""
    days_threshold = int(request.GET.get('days', 90))
    threshold_date = timezone.localdate() - timedelta(days=days_threshold)
    
    # Get batches that haven't been sold recently
    # First, get products that have been sold recently (exclude custom items)
    recently_sold = SaleItem.objects.filter(
        sale__sale_date__gte=threshold_date,
        sale__status='completed',
        is_custom=False,
        product__isnull=False
    ).values_list('product_id', flat=True).distinct()
    
    # Batches of products not sold recently
    dead_stock = ProductStock.objects.filter(
        quantity__gt=0
    ).exclude(
        product_id__in=list(recently_sold)
    ).select_related('product', 'warehouse').order_by('-quantity')
    
    # Calculate total dead stock value
    dead_stock_summary = dead_stock.aggregate(
        total_items=Sum('quantity'),
        total_value=Sum(F('quantity') * F('product__average_cost')),
        stock_count=Count('id'),
    )
    
    # Slow moving products (sold but low quantity, exclude custom items)
    slow_moving = SaleItem.objects.filter(
        sale__sale_date__gte=threshold_date,
        sale__status='completed',
        is_custom=False,
        product__isnull=False
    ).values(
        'product__id', 'product__sku', 'product__brand__name'
    ).annotate(
        quantity_sold=Sum(F('quantity') - F('returned_quantity'))
    ).filter(quantity_sold__lte=5).order_by('quantity_sold')
    
    # Paginate dead stock
    paginator = Paginator(dead_stock, 25)
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
    if export:
        pdf_context = {**context, 'dead_stock': dead_stock}

        def get_excel_data():
            data = []
            for stock in dead_stock:
                data.append([
                    stock.product.sku,
                    stock.product.brand.name if stock.product.brand else '-',
                    stock.product.category.name if stock.product.category else '-',
                    stock.warehouse.name,
                    stock.quantity,
                    stock.product.average_cost,
                    stock.quantity * stock.product.average_cost
                ])
            return data

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
        export_response = handle_export(
            request=request,
            context=pdf_context,
            filename='Dead_Stock_Report',
            pdf_template='reports/pdf/dead_stock_report.html',
            excel_title='Dead Stock Report',
            filters_dict=filters_dict,
            headers=['SKU', 'Brand', 'Category', 'Warehouse', 'Quantity', 'Buy Price', 'Total Value'],
            data_func=get_excel_data,
            totals=totals_row
        )
        if export_response:
            return export_response

    return render(request, 'reports/dead_stock_report.html', context)

