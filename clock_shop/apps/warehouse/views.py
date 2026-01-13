from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F
from django.http import JsonResponse
from django.utils import timezone
import json

from .models import Warehouse, StockTransfer, StockTransferItem
from .forms import WarehouseForm, StockTransferForm
from apps.inventory.models import Batch, Product
from apps.core.utils import create_audit_log


@login_required
def warehouse_list(request):
    """List all warehouses."""
    warehouses = Warehouse.objects.all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        warehouses = warehouses.filter(
            Q(name__icontains=search) | Q(code__icontains=search) | Q(address__icontains=search)
        )
    
    # Calculate stock info for each warehouse
    warehouse_list = list(warehouses)
    for warehouse in warehouse_list:
        warehouse.stock_value = warehouse.get_total_stock_value()
        warehouse.total_items = warehouse.get_total_items()
    
    paginator = Paginator(warehouse_list, 10)
    page = request.GET.get('page')
    warehouses = paginator.get_page(page)
    
    return render(request, 'warehouse/warehouse_list.html', {'warehouses': warehouses, 'search': search})


@login_required
def warehouse_detail(request, pk):
    """View warehouse details with stock information."""
    warehouse = get_object_or_404(Warehouse, pk=pk)
    
    # Get batches in this warehouse
    batches = Batch.objects.filter(
        warehouse=warehouse, 
        quantity__gt=0
    ).select_related('product', 'product__brand').order_by('product__sku')
    
    # Stock summary by product
    stock_summary = batches.values(
        'product__sku', 'product__brand__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_value=Sum(F('quantity') * F('buy_price'))
    ).order_by('product__sku')
    
    context = {
        'warehouse': warehouse,
        'batches': batches,
        'stock_summary': stock_summary,
        'total_value': warehouse.get_total_stock_value(),
        'total_items': warehouse.get_total_items(),
    }
    return render(request, 'warehouse/warehouse_detail.html', context)


@login_required
def warehouse_create(request):
    """Create a new warehouse."""
    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid():
            warehouse = form.save()
            create_audit_log(request, 'CREATE', warehouse)
            messages.success(request, f'Warehouse "{warehouse.name}" created.')
            return redirect('warehouse_list')
    else:
        form = WarehouseForm()
    
    return render(request, 'warehouse/warehouse_form.html', {'form': form, 'title': 'Add Warehouse'})


@login_required
def warehouse_edit(request, pk):
    """Edit a warehouse."""
    warehouse = get_object_or_404(Warehouse, pk=pk)
    
    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=warehouse)
        if form.is_valid():
            warehouse = form.save()
            create_audit_log(request, 'UPDATE', warehouse)
            messages.success(request, f'Warehouse "{warehouse.name}" updated.')
            return redirect('warehouse_detail', pk=warehouse.pk)
    else:
        form = WarehouseForm(instance=warehouse)
    
    return render(request, 'warehouse/warehouse_form.html', {
        'form': form,
        'title': 'Edit Warehouse',
        'warehouse': warehouse
    })


@login_required
def transfer_list(request):
    """List all stock transfers."""
    transfers = StockTransfer.objects.select_related(
        'source_warehouse', 'destination_warehouse', 'created_by'
    ).prefetch_related('items')
    
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
    
    paginator = Paginator(transfers, 10)
    page = request.GET.get('page')
    transfers = paginator.get_page(page)
    
    # Get warehouses for filter dropdowns
    warehouses = Warehouse.objects.filter(is_active=True)
    
    return render(request, 'warehouse/transfer_list.html', {
        'transfers': transfers,
        'warehouses': warehouses,
    })


@login_required
def transfer_create(request):
    """Create a new stock transfer."""
    warehouses = Warehouse.objects.filter(is_active=True)
    
    if request.method == 'POST':
        form = StockTransferForm(request.POST)
        items_data = request.POST.getlist('items')
        
        if form.is_valid() and items_data:
            transfer = form.save(commit=False)
            transfer.created_by = request.user
            transfer.save()
            
            for item_json in items_data:
                item = json.loads(item_json)
                batch = Batch.objects.get(pk=item['batch_id'])
                quantity = int(item['quantity'])
                
                if quantity > batch.quantity:
                    messages.error(request, f'Insufficient stock in batch {batch.batch_number}')
                    transfer.delete()
                    return redirect('transfer_create')
                
                StockTransferItem.objects.create(
                    transfer=transfer,
                    source_batch=batch,
                    quantity=quantity,
                )
            
            create_audit_log(request, 'TRANSFER', transfer, {
                'source': transfer.source_warehouse.name,
                'destination': transfer.destination_warehouse.name,
                'items': len(items_data)
            })
            
            messages.success(request, f'Transfer "{transfer.transfer_number}" created.')
            return redirect('transfer_detail', pk=transfer.pk)
    else:
        form = StockTransferForm(initial={'transfer_date': timezone.now()})
    
    context = {
        'form': form,
        'warehouses': warehouses,
    }
    return render(request, 'warehouse/transfer_form.html', context)


@login_required
def transfer_detail(request, pk):
    """View transfer details."""
    transfer = get_object_or_404(
        StockTransfer.objects.select_related(
            'source_warehouse', 'destination_warehouse', 'created_by'
        ).prefetch_related('items__source_batch__product'),
        pk=pk
    )
    return render(request, 'warehouse/transfer_detail.html', {'transfer': transfer})


@login_required
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
    
    return redirect('transfer_detail', pk=transfer.pk)


@login_required
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
    
    return redirect('transfer_detail', pk=transfer.pk)


@login_required
def api_warehouse_batches(request, warehouse_id):
    """API endpoint to get batches in a warehouse."""
    batches = Batch.objects.filter(
        warehouse_id=warehouse_id,
        quantity__gt=0
    ).select_related('product')
    
    data = [{
        'id': b.id,
        'batch_number': b.batch_number,
        'product_id': b.product.id,
        'product_sku': b.product.sku,
        'quantity': b.quantity,
        'buy_price': str(b.buy_price),
        'purchase_date': b.purchase_date.strftime('%Y-%m-%d'),
    } for b in batches]
    
    return JsonResponse(data, safe=False)
