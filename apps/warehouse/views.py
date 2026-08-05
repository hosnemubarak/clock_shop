from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.core.decorators import cashier_required, manager_required, admin_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, F
from django.http import JsonResponse
from django.utils import timezone
import json

from .models import Warehouse, StockTransfer, StockTransferItem
from .forms import WarehouseForm, StockTransferForm
from apps.inventory.models import ProductStock, Product
from apps.core.utils import create_audit_log, paginate


@cashier_required
def warehouse_list(request):
    """List all warehouses."""
    # Base queryset with annotations for stock value and items
    warehouses = Warehouse.objects.annotate(
        stock_value=Sum(F('product_stocks__quantity') * F('product_stocks__product__average_cost')),
        total_items=Sum('product_stocks__quantity')
    )
    
    # Search
    search = request.GET.get('search', '')
    if search:
        warehouses = warehouses.filter(
            Q(name__icontains=search) | Q(code__icontains=search) | Q(address__icontains=search)
        )

    total_warehouses = warehouses.count()
    active_shops = warehouses.filter(is_shop=True, is_active=True).count()

    warehouses = paginate(request, warehouses.order_by('name'), 10)

    return render(request, 'warehouse/warehouse_list.html', {
        'warehouses': warehouses,
        'search': search,
        'total_warehouses': total_warehouses,
        'active_shops': active_shops,
    })


@cashier_required
def warehouse_detail(request, pk):
    """View warehouse details with stock information."""
    warehouse = get_object_or_404(Warehouse, pk=pk)
    
    stocks = ProductStock.objects.filter(
        warehouse=warehouse,
        quantity__gt=0
    ).select_related('product', 'product__brand')

    # Product search
    product_search = request.GET.get('product_search', request.GET.get('search', ''))
    if product_search:
        stocks = stocks.filter(
            Q(product__sku__icontains=product_search) |
            Q(product__brand__name__icontains=product_search)
        )
    
    stocks = paginate(request, stocks, 10)

    context = {
        'warehouse': warehouse,
        'stocks': stocks,
        'total_value': warehouse.get_total_stock_value(),
        'total_items': warehouse.get_total_items(),
        'product_search': product_search,
    }
    return render(request, 'warehouse/warehouse_detail.html', context)


@cashier_required
def warehouse_create(request):
    """Create a new warehouse."""
    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                warehouse = form.save()
                # Nothing else enforces a single retail shop, so ticking the box
                # here has to clear it everywhere else.
                if warehouse.is_shop:
                    warehouse.set_as_shop()
            create_audit_log(request, 'CREATE', warehouse)
            messages.success(request, f'Warehouse "{warehouse.name}" created.')
            return redirect('warehouse:warehouse_list')
    else:
        form = WarehouseForm()
    
    return render(request, 'warehouse/warehouse_form.html', {'form': form, 'title': 'Add Warehouse'})


@cashier_required
def warehouse_edit(request, pk):
    """Edit a warehouse."""
    warehouse = get_object_or_404(Warehouse, pk=pk)
    
    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=warehouse)
        if form.is_valid():
            with transaction.atomic():
                warehouse = form.save()
                if warehouse.is_shop:
                    warehouse.set_as_shop()
            create_audit_log(request, 'UPDATE', warehouse)
            messages.success(request, f'Warehouse "{warehouse.name}" updated.')
            return redirect('warehouse:warehouse_detail', pk=warehouse.pk)
    else:
        form = WarehouseForm(instance=warehouse)
    
    return render(request, 'warehouse/warehouse_form.html', {
        'form': form,
        'title': 'Edit Warehouse',
        'warehouse': warehouse
    })


@cashier_required
def transfer_list(request):
    """List all stock transfers."""
    transfers = StockTransfer.objects.select_related(
        'source_warehouse', 'destination_warehouse', 'created_by'
    ).prefetch_related('items__product')
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        transfers = transfers.filter(status=status)
    
    # Filter by source warehouse
    source = request.GET.get('source')
    if source:
        transfers = transfers.filter(source_warehouse_id=source)
    
    # Filter by destination warehouse
    destination = request.GET.get('destination')
    if destination:
        transfers = transfers.filter(destination_warehouse_id=destination)
    
    transfers = paginate(request, transfers, 10)

    # Get warehouses for filter dropdowns
    warehouses = Warehouse.objects.filter(is_active=True)

    return render(request, 'warehouse/transfer_list.html', {
        'transfers': transfers,
        'warehouses': warehouses,
    })


@cashier_required
def transfer_create(request):
    """Create a new stock transfer."""
    warehouses = Warehouse.objects.filter(is_active=True)
    
    if request.method == 'POST':
        form = StockTransferForm(request.POST)
        items_data = request.POST.getlist('items')
        
        if form.is_valid() and items_data:
            # Parse and coerce the whole payload before touching the database, so
            # malformed input can never leave a half-built transfer behind.
            requested = {}
            try:
                for item_json in items_data:
                    item = json.loads(item_json)
                    product_id = int(item['product_id'])
                    quantity = int(item['quantity'])
                    if quantity < 1:
                        raise ValueError('Quantity must be at least 1.')
                    # Two lines for the same product each pass an individual
                    # stock check but together can over-draw, so merge them.
                    requested[product_id] = requested.get(product_id, 0) + quantity
            except (ValueError, TypeError, KeyError):
                messages.error(request, 'Invalid items data format.')
                return redirect('warehouse:transfer_create')

            try:
                with transaction.atomic():
                    transfer = form.save(commit=False)
                    transfer.created_by = request.user
                    transfer.save()

                    products_map = {
                        p.id: p for p in Product.objects.filter(id__in=requested)
                    }
                    # Lock the source rows before checking them. Reading unlocked
                    # stock let two concurrent transfers both pass the check and
                    # draw the same units twice.
                    stocks_map = {
                        s.product_id: s
                        for s in ProductStock.objects.select_for_update().filter(
                            product_id__in=requested,
                            warehouse=transfer.source_warehouse,
                        ).order_by('product_id')
                    }

                    items = []
                    for product_id, quantity in requested.items():
                        product = products_map.get(product_id)
                        if not product:
                            raise ValueError(f'Product {product_id} no longer exists.')

                        stock = stocks_map.get(product_id)
                        available = stock.quantity if stock else 0
                        if quantity > available:
                            raise ValueError(
                                f'Insufficient stock for {product.display_name} '
                                f'(requested {quantity}, available {available}).'
                            )

                        items.append(StockTransferItem(
                            transfer=transfer,
                            product=product,
                            quantity=quantity,
                        ))

                    StockTransferItem.objects.bulk_create(items)

                    create_audit_log(request, 'TRANSFER', transfer, {
                        'source': transfer.source_warehouse.name,
                        'destination': transfer.destination_warehouse.name,
                        'items': len(items),
                    })
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('warehouse:transfer_create')

            messages.success(request, f'Transfer "{transfer.transfer_number}" created.')
            return redirect('warehouse:transfer_detail', pk=transfer.pk)
    else:
        form = StockTransferForm(initial={'transfer_date': timezone.now()})
    
    context = {
        'form': form,
        'warehouses': warehouses,
        'has_multiple_warehouses': warehouses.count() >= 2,
    }
    return render(request, 'warehouse/transfer_form.html', context)


@cashier_required
def transfer_detail(request, pk):
    """View transfer details."""
    transfer = get_object_or_404(
        StockTransfer.objects.select_related(
            'source_warehouse', 'destination_warehouse', 'created_by'
        ).prefetch_related('items__product'),
        pk=pk
    )
    return render(request, 'warehouse/transfer_detail.html', {'transfer': transfer})


@cashier_required
def transfer_complete(request, pk):
    """Complete a pending transfer."""
    transfer = get_object_or_404(StockTransfer, pk=pk)
    
    if request.method == 'POST':
        if transfer.status != 'pending':
            messages.error(request, 'Transfer is not pending.')
        else:
            try:
                transfer.complete_transfer()
                create_audit_log(request, 'TRANSFER', transfer, {
                    'action': 'completed',
                    'source': transfer.source_warehouse.name,
                    'destination': transfer.destination_warehouse.name,
                })
                messages.success(request, f'Transfer "{transfer.transfer_number}" completed.')
            except ValueError as e:
                messages.error(request, str(e))
    
    return redirect('warehouse:transfer_detail', pk=transfer.pk)


@cashier_required
def transfer_cancel(request, pk):
    """Cancel a pending transfer."""
    transfer = get_object_or_404(StockTransfer, pk=pk)
    
    if request.method == 'POST':
        if transfer.status != 'pending':
            messages.error(request, 'Transfer is not pending.')
        else:
            transfer.status = 'cancelled'
            transfer.save()
            create_audit_log(request, 'TRANSFER', transfer, {'action': 'cancelled'})
            messages.success(request, f'Transfer "{transfer.transfer_number}" cancelled.')
    
    return redirect('warehouse:transfer_detail', pk=transfer.pk)


@cashier_required
def api_warehouse_stocks(request, warehouse_id):
    """API endpoint to get stocks in a warehouse. Delegates to the inventory
    app's superset implementation, which supports ?product= filtering."""
    from apps.inventory.views import api_warehouse_stocks as inventory_impl
    return inventory_impl(request, warehouse_id)
