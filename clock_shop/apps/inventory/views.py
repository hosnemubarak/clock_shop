from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from decimal import Decimal
from datetime import date

from .models import Product, Category, Brand, Batch, Purchase, PurchaseItem, StockOut, StockOutItem
from .forms import (ProductForm, CategoryForm, BrandForm, BatchForm, 
                    PurchaseForm, PurchaseItemForm, StockOutForm)
from apps.warehouse.models import Warehouse
from apps.core.utils import create_audit_log


@login_required
def product_list(request):
    """List all products with filtering."""
    products = Product.objects.select_related('category', 'brand').all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        products = products.filter(
            Q(sku__icontains=search) |
            Q(brand__name__icontains=search)
        )
    
    # Category filter
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)
    
    # Brand filter
    brand_id = request.GET.get('brand')
    if brand_id:
        products = products.filter(brand_id=brand_id)
    
    # Stock filter
    stock_filter = request.GET.get('stock')
    if stock_filter == 'low':
        products = products.filter(total_stock__gt=0, total_stock__lte=10)
    elif stock_filter == 'out':
        products = products.filter(total_stock=0)
    elif stock_filter == 'in':
        products = products.filter(total_stock__gt=0)
    
    # Status filter
    status_filter = request.GET.get('status')
    if status_filter == 'active':
        products = products.filter(is_active=True)
    elif status_filter == 'inactive':
        products = products.filter(is_active=False)
    
    paginator = Paginator(products, 10)
    page = request.GET.get('page')
    products = paginator.get_page(page)
    
    categories = Category.objects.filter(is_active=True)
    brands = Brand.objects.filter(is_active=True)
    
    context = {
        'products': products,
        'categories': categories,
        'brands': brands,
        'search': search,
        'selected_category': category_id,
        'selected_brand': request.GET.get('brand', ''),
        'selected_stock': stock_filter or '',
        'selected_status': request.GET.get('status', ''),
    }
    return render(request, 'inventory/product_list.html', context)


@login_required
def product_detail(request, pk):
    """View product details with batch information."""
    product = get_object_or_404(Product, pk=pk)
    batches = product.batches.select_related('warehouse').filter(quantity__gt=0)
    all_batches = product.batches.select_related('warehouse').all()[:20]
    
    context = {
        'product': product,
        'available_batches': batches,
        'all_batches': all_batches,
    }
    return render(request, 'inventory/product_detail.html', context)


@login_required
def product_create(request):
    """Create a new product."""
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            create_audit_log(request, 'CREATE', product)
            messages.success(request, f'Product "{product.display_name}" created successfully.')
            return redirect('product_list')
    else:
        form = ProductForm()
    
    return render(request, 'inventory/product_form.html', {'form': form, 'title': 'Add Product'})


@login_required
def product_edit(request, pk):
    """Edit a product."""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            product = form.save()
            create_audit_log(request, 'UPDATE', product)
            messages.success(request, f'Product "{product.display_name}" updated successfully.')
            return redirect('product_detail', pk=product.pk)
    else:
        form = ProductForm(instance=product)
    
    return render(request, 'inventory/product_form.html', {
        'form': form, 
        'title': 'Edit Product',
        'product': product
    })


@login_required
def product_delete(request, pk):
    """Delete a product."""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        if product.batches.exists():
            messages.error(request, 'Cannot delete product with existing batches.')
        else:
            display_name = product.display_name
            create_audit_log(request, 'DELETE', product)
            product.delete()
            messages.success(request, f'Product "{display_name}" deleted successfully.')
            return redirect('product_list')
    
    return render(request, 'inventory/product_confirm_delete.html', {'product': product})


@login_required
def category_list(request):
    """List all categories."""
    categories = Category.objects.annotate(product_count=Sum('products__total_stock'))
    
    # Search
    search = request.GET.get('search', '')
    if search:
        categories = categories.filter(Q(name__icontains=search) | Q(description__icontains=search))
    
    paginator = Paginator(categories, 10)
    page = request.GET.get('page')
    categories = paginator.get_page(page)
    
    return render(request, 'inventory/category_list.html', {'categories': categories, 'search': search})


@login_required
def category_create(request):
    """Create a new category."""
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            create_audit_log(request, 'CREATE', category)
            messages.success(request, f'Category "{category.name}" created.')
            return redirect('category_list')
    else:
        form = CategoryForm()
    
    return render(request, 'inventory/category_form.html', {'form': form, 'title': 'Add Category'})


@login_required
def category_edit(request, pk):
    """Edit a category."""
    category = get_object_or_404(Category, pk=pk)
    
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            create_audit_log(request, 'UPDATE', category)
            messages.success(request, f'Category "{category.name}" updated.')
            return redirect('category_list')
    else:
        form = CategoryForm(instance=category)
    
    return render(request, 'inventory/category_form.html', {
        'form': form, 
        'title': 'Edit Category',
        'category': category
    })


@login_required
def brand_list(request):
    """List all brands."""
    brands = Brand.objects.all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        brands = brands.filter(Q(name__icontains=search) | Q(description__icontains=search))
    
    paginator = Paginator(brands, 10)
    page = request.GET.get('page')
    brands = paginator.get_page(page)
    
    return render(request, 'inventory/brand_list.html', {'brands': brands, 'search': search})


@login_required
def brand_create(request):
    """Create a new brand."""
    if request.method == 'POST':
        form = BrandForm(request.POST)
        if form.is_valid():
            brand = form.save()
            create_audit_log(request, 'CREATE', brand)
            messages.success(request, f'Brand "{brand.name}" created.')
            return redirect('brand_list')
    else:
        form = BrandForm()
    
    return render(request, 'inventory/brand_form.html', {'form': form, 'title': 'Add Brand'})


@login_required
def brand_edit(request, pk):
    """Edit a brand."""
    brand = get_object_or_404(Brand, pk=pk)
    
    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand)
        if form.is_valid():
            brand = form.save()
            create_audit_log(request, 'UPDATE', brand)
            messages.success(request, f'Brand "{brand.name}" updated.')
            return redirect('brand_list')
    else:
        form = BrandForm(instance=brand)
    
    return render(request, 'inventory/brand_form.html', {
        'form': form, 
        'title': 'Edit Brand',
        'brand': brand
    })


@login_required
def batch_list(request):
    """List all batches with filtering."""
    batches = Batch.objects.select_related('product', 'warehouse').all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        batches = batches.filter(
            Q(batch_number__icontains=search) |
            Q(product__sku__icontains=search) |
            Q(product__brand__name__icontains=search) |
            Q(supplier__icontains=search)
        )
    
    # Warehouse filter
    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        batches = batches.filter(warehouse_id=warehouse_id)
    
    # Stock filter
    stock_filter = request.GET.get('stock')
    if stock_filter == 'available':
        batches = batches.filter(quantity__gt=0)
    elif stock_filter == 'depleted':
        batches = batches.filter(quantity=0)
    
    paginator = Paginator(batches, 10)
    page = request.GET.get('page')
    batches = paginator.get_page(page)
    
    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'batches': batches,
        'warehouses': warehouses,
        'search': search,
    }
    return render(request, 'inventory/batch_list.html', context)


@login_required
def batch_create(request):
    """Create a new batch (stock in)."""
    if request.method == 'POST':
        form = BatchForm(request.POST)
        if form.is_valid():
            batch = form.save()
            create_audit_log(request, 'STOCK_IN', batch, {
                'quantity': batch.quantity,
                'buy_price': str(batch.buy_price),
                'warehouse': batch.warehouse.name
            })
            messages.success(request, f'Batch "{batch.batch_number}" created with {batch.quantity} units.')
            return redirect('batch_list')
    else:
        form = BatchForm(initial={'purchase_date': date.today()})
    
    return render(request, 'inventory/batch_form.html', {'form': form, 'title': 'Add Stock (New Batch)'})


@login_required
def batch_detail(request, pk):
    """View batch details."""
    batch = get_object_or_404(Batch.objects.select_related('product', 'warehouse'), pk=pk)
    return render(request, 'inventory/batch_detail.html', {'batch': batch})


@login_required
def purchase_list(request):
    """List all purchases."""
    purchases = Purchase.objects.select_related('created_by').prefetch_related('items')
    
    paginator = Paginator(purchases, 10)
    page = request.GET.get('page')
    purchases = paginator.get_page(page)
    
    return render(request, 'inventory/purchase_list.html', {'purchases': purchases})


@login_required
def purchase_create(request):
    """Create a new purchase order with items."""
    warehouses = Warehouse.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True)
    
    if request.method == 'POST':
        form = PurchaseForm(request.POST)
        items_data = request.POST.getlist('items')
        
        if form.is_valid() and items_data:
            import json
            purchase = form.save(commit=False)
            purchase.created_by = request.user
            purchase.total_amount = Decimal('0')
            purchase.save()
            
            total = Decimal('0')
            for item_json in items_data:
                item = json.loads(item_json)
                product = Product.objects.get(pk=item['product_id'])
                warehouse = Warehouse.objects.get(pk=item['warehouse_id'])
                quantity = int(item['quantity'])
                unit_price = Decimal(item['unit_price'])
                
                # Create batch
                batch = Batch.objects.create(
                    product=product,
                    warehouse=warehouse,
                    buy_price=unit_price,
                    initial_quantity=quantity,
                    quantity=quantity,
                    purchase_date=purchase.purchase_date,
                    supplier=purchase.supplier,
                )
                
                # Create purchase item
                PurchaseItem.objects.create(
                    purchase=purchase,
                    batch=batch,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                )
                
                total += quantity * unit_price
                product.update_total_stock()
            
            purchase.total_amount = total
            purchase.save()
            
            create_audit_log(request, 'CREATE', purchase, {'total': str(total)})
            messages.success(request, f'Purchase "{purchase.purchase_number}" created.')
            return redirect('purchase_list')
    else:
        form = PurchaseForm(initial={'purchase_date': date.today()})
    
    context = {
        'form': form,
        'warehouses': warehouses,
        'products': products,
    }
    return render(request, 'inventory/purchase_form.html', context)


@login_required
def purchase_detail(request, pk):
    """View purchase details."""
    purchase = get_object_or_404(
        Purchase.objects.select_related('created_by').prefetch_related('items__product', 'items__batch'),
        pk=pk
    )
    return render(request, 'inventory/purchase_detail.html', {'purchase': purchase})


@login_required
def api_product_batches(request, product_id):
    """API endpoint to get available batches for a product."""
    warehouse_id = request.GET.get('warehouse')
    batches = Batch.objects.filter(product_id=product_id, quantity__gt=0)
    
    if warehouse_id:
        batches = batches.filter(warehouse_id=warehouse_id)
    
    data = [{
        'id': b.id,
        'batch_number': b.batch_number,
        'quantity': b.quantity,
        'buy_price': str(b.buy_price),
        'warehouse': b.warehouse.name,
        'purchase_date': b.purchase_date.strftime('%Y-%m-%d'),
    } for b in batches]
    
    return JsonResponse(data, safe=False)


# Stock Out Views
@login_required
def stockout_list(request):
    """List all stock out records."""
    stockouts = StockOut.objects.select_related('warehouse', 'created_by').all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        stockouts = stockouts.filter(
            Q(stockout_number__icontains=search) |
            Q(notes__icontains=search)
        )
    
    # Warehouse filter
    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        stockouts = stockouts.filter(warehouse_id=warehouse_id)
    
    # Reason filter
    reason = request.GET.get('reason')
    if reason:
        stockouts = stockouts.filter(reason=reason)
    
    # Status filter
    status = request.GET.get('status')
    if status:
        stockouts = stockouts.filter(status=status)
    
    paginator = Paginator(stockouts, 10)
    page = request.GET.get('page')
    stockouts = paginator.get_page(page)
    
    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'stockouts': stockouts,
        'warehouses': warehouses,
        'reason_choices': StockOut.REASON_CHOICES,
        'status_choices': StockOut.STATUS_CHOICES,
        'search': search,
    }
    return render(request, 'inventory/stockout_list.html', context)


@login_required
def stockout_create(request):
    """Create a new stock out record."""
    from django.utils import timezone
    import json
    
    warehouses = Warehouse.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True, total_stock__gt=0)
    
    if request.method == 'POST':
        form = StockOutForm(request.POST)
        items_data = request.POST.get('items_data', '[]')
        
        try:
            items_list = json.loads(items_data)
        except json.JSONDecodeError:
            items_list = []
        
        if form.is_valid() and items_list:
            stockout = form.save(commit=False)
            stockout.created_by = request.user
            stockout.save()
            
            # Create stock out items
            for item in items_list:
                batch = Batch.objects.get(pk=item['batch_id'])
                StockOutItem.objects.create(
                    stockout=stockout,
                    batch=batch,
                    quantity=int(item['quantity']),
                    cost_price=batch.buy_price
                )
            
            # Complete the stock out immediately
            try:
                stockout.complete_stockout()
                create_audit_log(request, 'STOCK_OUT', stockout, {
                    'reason': stockout.get_reason_display(),
                    'total_value': str(stockout.total_value),
                    'items_count': len(items_list)
                })
                messages.success(request, f'Stock out "{stockout.stockout_number}" completed successfully.')
            except ValueError as e:
                messages.error(request, str(e))
                stockout.delete()
                return redirect('stockout_create')
            
            return redirect('stockout_detail', pk=stockout.pk)
        else:
            if not items_list:
                messages.error(request, 'Please add at least one item.')
    else:
        form = StockOutForm(initial={'stockout_date': timezone.now()})
    
    context = {
        'form': form,
        'warehouses': warehouses,
        'products': products,
        'reason_choices': StockOut.REASON_CHOICES,
    }
    return render(request, 'inventory/stockout_form.html', context)


@login_required
def stockout_detail(request, pk):
    """View stock out details."""
    stockout = get_object_or_404(
        StockOut.objects.select_related('warehouse', 'created_by').prefetch_related(
            'items__batch__product', 'items__batch__warehouse'
        ),
        pk=pk
    )
    return render(request, 'inventory/stockout_detail.html', {'stockout': stockout})


@login_required
def stockout_cancel(request, pk):
    """Cancel a stock out record."""
    stockout = get_object_or_404(StockOut, pk=pk)
    
    if request.method == 'POST':
        try:
            stockout.cancel_stockout()
            create_audit_log(request, 'STOCK_OUT_CANCEL', stockout, {
                'reason': stockout.get_reason_display(),
            })
            messages.success(request, f'Stock out "{stockout.stockout_number}" cancelled. Stock restored.')
        except ValueError as e:
            messages.error(request, str(e))
    
    return redirect('stockout_detail', pk=pk)


@login_required
def api_warehouse_batches(request, warehouse_id):
    """API endpoint to get available batches for a warehouse."""
    product_id = request.GET.get('product')
    batches = Batch.objects.filter(warehouse_id=warehouse_id, quantity__gt=0).select_related('product')
    
    if product_id:
        batches = batches.filter(product_id=product_id)
    
    data = [{
        'id': b.id,
        'batch_number': b.batch_number,
        'product_id': b.product_id,
        'product_name': b.product.display_name,
        'quantity': b.quantity,
        'buy_price': str(b.buy_price),
        'purchase_date': b.purchase_date.strftime('%Y-%m-%d'),
    } for b in batches]
    
    return JsonResponse(data, safe=False)
