from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.core.decorators import cashier_required, manager_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, ProtectedError
from django.http import JsonResponse
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import json
import logging

from .models import Product, Category, Brand, ProductStock, Purchase, PurchaseItem, StockOut, StockOutItem
from .forms import (ProductForm, CategoryForm, BrandForm, 
                    PurchaseForm, PurchaseItemForm, StockOutForm)
from apps.warehouse.models import Warehouse
from apps.core.utils import create_audit_log, paginate

logger = logging.getLogger(__name__)


@cashier_required
def product_list(request):
    """List all products with filtering."""
    products = Product.objects.select_related('category', 'brand').order_by('-updated_at')
    
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
        from apps.core.models import SystemSettings
        threshold = SystemSettings.get_settings().low_stock_threshold or 5
        products = products.filter(total_stock__gt=0, total_stock__lte=threshold)
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
    
    products = paginate(request, products, 10)

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
        'warehouses': Warehouse.objects.filter(is_active=True),
    }
    return render(request, 'inventory/product_list.html', context)


@cashier_required
def product_detail(request, pk):
    """View product details with stock information."""
    product = get_object_or_404(Product, pk=pk)
    stocks = product.stocks.select_related('warehouse').all()
    
    context = {
        'product': product,
        'stocks': stocks,
        'warehouses': Warehouse.objects.filter(is_active=True),
    }
    return render(request, 'inventory/product_detail.html', context)


@manager_required
def product_create(request):
    """Create a new product."""
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            # Handle initial stock
            initial_stock = form.cleaned_data.get('initial_stock')
            initial_cost_price = form.cleaned_data.get('initial_cost_price')
            initial_warehouse = form.cleaned_data.get('initial_warehouse')
            initial_stock_supplier = form.cleaned_data.get('initial_stock_supplier')
            initial_stock_date = form.cleaned_data.get('initial_stock_date')
            initial_stock_notes = form.cleaned_data.get('initial_stock_notes')
            add_initial_stock = bool(initial_stock and initial_warehouse)

            # One transaction for the product, its opening purchase, the stock row
            # and both denormalised aggregates. A failure part-way through used to
            # leave a product whose average_cost and total_stock disagreed with the
            # PurchaseItem rows behind it.
            with transaction.atomic():
                product = form.save()
                create_audit_log(request, 'CREATE', product)

                if add_initial_stock:
                    if initial_cost_price is None:
                        initial_cost_price = Decimal('0.00')

                    # Create a Purchase to record the initial stock
                    purchase = Purchase.objects.create(
                        supplier=initial_stock_supplier,
                        purchase_date=initial_stock_date,
                        total_amount=initial_stock * initial_cost_price,
                        notes=initial_stock_notes or 'Initial stock during product creation',
                        created_by=request.user
                    )

                    PurchaseItem.objects.create(
                        purchase=purchase,
                        product=product,
                        warehouse=initial_warehouse,
                        quantity=initial_stock,
                        unit_price=initial_cost_price
                    )

                    stock, _ = ProductStock.objects.get_or_create(
                        product=product,
                        warehouse=initial_warehouse,
                        defaults={'quantity': 0}
                    )
                    stock.quantity += initial_stock
                    stock.save()

                    # WAC first (it weights against the previous total_stock), then
                    # refresh the denormalised total. Without update_total_stock()
                    # the product stays at total_stock=0 and is invisible to the POS
                    # and sale form, both of which filter on total_stock__gt=0.
                    product.recalculate_average_cost(initial_stock, initial_cost_price)
                    product.update_total_stock()

            if add_initial_stock:
                messages.success(request, f'Product "{product.display_name}" created with {initial_stock} initial stock.')
            else:
                messages.success(request, f'Product "{product.display_name}" created successfully.')

            return redirect('inventory:product_list')
    else:
        form = ProductForm()
    
    return render(request, 'inventory/product_form.html', {'form': form, 'title': 'Add Product'})


@manager_required
def product_edit(request, pk):
    """Edit a product."""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            product = form.save()
            create_audit_log(request, 'UPDATE', product)
            messages.success(request, f'Product "{product.display_name}" updated successfully.')
            return redirect('inventory:product_detail', pk=product.pk)
    else:
        form = ProductForm(instance=product)
    
    return render(request, 'inventory/product_form.html', {
        'form': form, 
        'title': 'Edit Product',
        'product': product
    })


@manager_required
def product_delete(request, pk):
    """Delete a product."""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        if product.stocks.filter(quantity__gt=0).exists():
            messages.error(
                request, 
                'Cannot delete this product because it has existing stock. '
                'Please stock out all quantities before attempting to delete the product.'
            )
        else:
            display_name = product.display_name
            try:
                product.delete()
                create_audit_log(request, 'DELETE', product)
                messages.success(request, f'Product "{display_name}" deleted successfully.')
                return redirect('inventory:product_list')
            except ProtectedError:
                messages.error(
                    request, 
                    f'Cannot delete "{display_name}" because it has associated transaction history (e.g. stock additions or stock outs). '
                    'To remove it from the catalog, please mark it as inactive instead.'
                )
    
    return render(request, 'inventory/product_confirm_delete.html', {'product': product})


@manager_required
def category_list(request):
    """List all categories."""
    categories = Category.objects.annotate(product_count=Sum('products__total_stock'))
    
    # Search
    search = request.GET.get('search', '')
    if search:
        categories = categories.filter(Q(name__icontains=search) | Q(description__icontains=search))
    
    categories = paginate(request, categories, 10)

    return render(request, 'inventory/category_list.html', {'categories': categories, 'search': search})


@manager_required
def category_create(request):
    """Create a new category."""
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            create_audit_log(request, 'CREATE', category)
            messages.success(request, f'Category "{category.name}" created.')
            return redirect('inventory:category_list')
    else:
        form = CategoryForm()
    
    return render(request, 'inventory/category_form.html', {'form': form, 'title': 'Add Category'})


@manager_required
def category_edit(request, pk):
    """Edit a category."""
    category = get_object_or_404(Category, pk=pk)
    
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            create_audit_log(request, 'UPDATE', category)
            messages.success(request, f'Category "{category.name}" updated.')
            return redirect('inventory:category_list')
    else:
        form = CategoryForm(instance=category)
    
    return render(request, 'inventory/category_form.html', {
        'form': form, 
        'title': 'Edit Category',
        'category': category
    })


@manager_required
def brand_list(request):
    """List all brands."""
    brands = Brand.objects.all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        brands = brands.filter(Q(name__icontains=search) | Q(description__icontains=search))
    
    brands = paginate(request, brands, 10)

    return render(request, 'inventory/brand_list.html', {'brands': brands, 'search': search})


@manager_required
def brand_create(request):
    """Create a new brand."""
    if request.method == 'POST':
        form = BrandForm(request.POST)
        if form.is_valid():
            brand = form.save()
            create_audit_log(request, 'CREATE', brand)
            messages.success(request, f'Brand "{brand.name}" created.')
            return redirect('inventory:brand_list')
    else:
        form = BrandForm()
    
    return render(request, 'inventory/brand_form.html', {'form': form, 'title': 'Add Brand'})


@manager_required
def brand_edit(request, pk):
    """Edit a brand."""
    brand = get_object_or_404(Brand, pk=pk)
    
    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand)
        if form.is_valid():
            brand = form.save()
            create_audit_log(request, 'UPDATE', brand)
            messages.success(request, f'Brand "{brand.name}" updated.')
            return redirect('inventory:brand_list')
    else:
        form = BrandForm(instance=brand)
    
    return render(request, 'inventory/brand_form.html', {
        'form': form, 
        'title': 'Edit Brand',
        'brand': brand
    })





@manager_required
def purchase_list(request):
    """List all purchases."""
    purchases = Purchase.objects.select_related('created_by').prefetch_related('items')
    
    purchases = paginate(request, purchases, 10)

    return render(request, 'inventory/purchase_list.html', {'purchases': purchases})


@manager_required
def purchase_create(request):
    """Create a new purchase order with items."""
    warehouses = Warehouse.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True)
    
    if request.method == 'POST':
        form = PurchaseForm(request.POST)
        items_data = request.POST.getlist('items')
        
        if form.is_valid() and items_data:
            # Coerce the whole payload before touching the database. The old code
            # parsed each line inside the write loop, so a malformed line #3 raised
            # after lines #1-2 had already moved stock and shifted the average cost,
            # with no transaction to roll any of it back.
            parsed_items = []
            try:
                for item_json in items_data:
                    item = json.loads(item_json)
                    quantity = int(item['quantity'])
                    if quantity < 1:
                        raise ValueError('Quantity must be at least 1.')
                    unit_price = Decimal(str(item['unit_price']))
                    if unit_price < 0:
                        raise ValueError('Unit price cannot be negative.')
                    parsed_items.append({
                        'product_id': int(item['product_id']),
                        'warehouse_id': int(item['warehouse_id']),
                        'quantity': quantity,
                        'unit_price': unit_price,
                    })
            except (ValueError, TypeError, KeyError, InvalidOperation):
                messages.error(request, 'Invalid items data format.')
                return redirect('inventory:purchase_create')

            try:
                with transaction.atomic():
                    purchase = form.save(commit=False)
                    purchase.created_by = request.user
                    purchase.total_amount = Decimal('0')
                    purchase.save()

                    # Prefetch to prevent N+1
                    product_ids = {item['product_id'] for item in parsed_items}
                    warehouse_ids = {item['warehouse_id'] for item in parsed_items}
                    products_map = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
                    warehouses_map = {w.id: w for w in Warehouse.objects.filter(id__in=warehouse_ids)}

                    # Lock the stock rows before reading them. Two concurrent stock-ins
                    # on the same product used to read the same quantity and one of the
                    # two increments was lost. The order_by keeps the lock order stable
                    # so concurrent requests queue instead of deadlocking.
                    stocks_map = {
                        (s.product_id, s.warehouse_id): s
                        for s in ProductStock.objects.select_for_update().filter(
                            product_id__in=product_ids,
                            warehouse_id__in=warehouse_ids,
                        ).order_by('product_id', 'warehouse_id')
                    }

                    total = Decimal('0')
                    items = []

                    for item in parsed_items:
                        product = products_map.get(item['product_id'])
                        warehouse = warehouses_map.get(item['warehouse_id'])
                        if not product or not warehouse:
                            # Skipping the line used to bank the rest of the stock-in
                            # against a total that did not match its own items.
                            raise ValueError('A selected product or warehouse no longer exists.')

                        quantity = item['quantity']
                        unit_price = item['unit_price']

                        key = (product.id, warehouse.id)
                        stock = stocks_map.get(key)
                        if stock is None:
                            stock, _ = ProductStock.objects.get_or_create(
                                product=product,
                                warehouse=warehouse,
                                defaults={'quantity': 0}
                            )
                            stocks_map[key] = stock
                        stock.quantity += quantity
                        stock.save(update_fields=['quantity'])

                        # Weighted average cost first: it weights the incoming units
                        # against the previous total_stock, so refreshing the total
                        # before it would double-count this line's quantity.
                        product.recalculate_average_cost(quantity, unit_price)
                        product.update_total_stock()

                        items.append(PurchaseItem(
                            purchase=purchase,
                            product=product,
                            warehouse=warehouse,
                            quantity=quantity,
                            unit_price=unit_price,
                        ))
                        total += quantity * unit_price

                    PurchaseItem.objects.bulk_create(items)

                    purchase.total_amount = total
                    purchase.save(update_fields=['total_amount'])

                    create_audit_log(request, 'CREATE', purchase, {'total': str(total)})
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('inventory:purchase_create')

            messages.success(request, f'Stock In record "{purchase.purchase_number}" created.')
            return redirect('inventory:purchase_list')
    else:
        form = PurchaseForm(initial={'purchase_date': timezone.localdate()})
    
    context = {
        'form': form,
        'warehouses': warehouses,
        'products': products,
    }
    return render(request, 'inventory/purchase_form.html', context)


@manager_required
def purchase_detail(request, pk):
    """View purchase details."""
    purchase = get_object_or_404(
        Purchase.objects.select_related('created_by').prefetch_related('items__product', 'items__warehouse'),
        pk=pk
    )
    return render(request, 'inventory/purchase_detail.html', {'purchase': purchase})


@cashier_required
def api_product_stocks(request, product_id):
    """API endpoint to get available stocks for a product."""
    warehouse_id = request.GET.get('warehouse')
    stocks = ProductStock.objects.filter(product_id=product_id, quantity__gt=0)
    
    if warehouse_id:
        stocks = stocks.filter(warehouse_id=warehouse_id)
    
    data = [{
        'id': s.id,
        'quantity': s.quantity,
        'warehouse': s.warehouse.name,
        'average_cost': str(s.product.average_cost),
    } for s in stocks]
    
    return JsonResponse(data, safe=False)


@manager_required
def api_quick_add_stock(request, product_id):
    """API endpoint to quickly add stock to a product."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
    product = get_object_or_404(Product, pk=product_id)
    
    # Coerce the whole payload before touching the database. int()/Decimal() on
    # untrusted input used to raise from the middle of the write sequence, and
    # InvalidOperation is not a ValueError so it escaped into the blanket handler.
    try:
        data = json.loads(request.body)
        warehouse_id = data.get('warehouse_id')
        quantity = int(data.get('quantity', 0))
        unit_price = Decimal(str(data.get('unit_price', '0.00')))
        supplier = data.get('supplier')
        purchase_date_str = data.get('purchase_date')
    except (ValueError, TypeError, AttributeError, InvalidOperation):
        return JsonResponse({'success': False, 'error': 'Invalid request data.'}, status=400)

    notes = data.get('notes') or f'Quick stock addition for {product.display_name}'

    if not warehouse_id or quantity <= 0 or not purchase_date_str:
        return JsonResponse({'success': False, 'error': 'Warehouse, positive quantity, and purchase date are required.'}, status=400)

    if unit_price < 0:
        return JsonResponse({'success': False, 'error': 'Unit price cannot be negative.'}, status=400)

    warehouse = get_object_or_404(Warehouse, pk=warehouse_id)

    # datetime is not imported at module level; this import is load-bearing.
    import datetime

    try:
        purchase_date = datetime.datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid purchase date format.'}, status=400)

    try:
        with transaction.atomic():
            # Record the addition as a Purchase so the cost history stays auditable.
            purchase = Purchase.objects.create(
                supplier=supplier,
                purchase_date=purchase_date,
                total_amount=quantity * unit_price,
                notes=notes,
                created_by=request.user
            )

            PurchaseItem.objects.create(
                purchase=purchase,
                product=product,
                warehouse=warehouse,
                quantity=quantity,
                unit_price=unit_price
            )

            # Lock the stock row before reading it. Two concurrent additions used
            # to read the same quantity and one of the increments was lost.
            stock, _ = ProductStock.objects.select_for_update().get_or_create(
                product=product,
                warehouse=warehouse,
                defaults={'quantity': 0}
            )
            stock.quantity += quantity
            stock.save(update_fields=['quantity'])

            # Weighted average cost first: it weights the incoming units against
            # the previous total_stock, so refreshing the total before it would
            # double-count this quantity.
            product.recalculate_average_cost(quantity, unit_price)
            product.update_total_stock()

            create_audit_log(request, 'UPDATE', product, {'notes': f"Quick added {quantity} stock to {warehouse.name}"})
    except Exception:
        # The old handler returned str(e) at status 400, which leaked internals
        # and reported server faults as client errors.
        logger.exception('Quick add stock failed for product %s', product_id)
        return JsonResponse({'success': False, 'error': 'Could not add stock. Please try again.'}, status=500)

    return JsonResponse({'success': True, 'message': f'Successfully added {quantity} stock.'})


# Stock Out Views
@manager_required
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
    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        stockouts = stockouts.filter(warehouse_id=warehouse_id)

    # Reason filter
    reason = request.GET.get('reason', '')
    if reason:
        stockouts = stockouts.filter(reason=reason)

    # Status filter
    status = request.GET.get('status', '')
    if status:
        stockouts = stockouts.filter(status=status)
    
    stockouts = paginate(request, stockouts, 10)

    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'stockouts': stockouts,
        'warehouses': warehouses,
        'reason_choices': StockOut.Reason.choices,
        'status_choices': StockOut.Status.choices,
        'search': search,
        'warehouse_id': warehouse_id,
        'reason': reason,
        'status': status,
    }
    return render(request, 'inventory/stockout_list.html', context)


@manager_required
def stockout_create(request):
    """Create a new stock out record."""
    warehouses = Warehouse.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True, total_stock__gt=0)

    if request.method == 'POST':
        form = StockOutForm(request.POST)
        items_data = request.POST.get('items_data', '[]')

        parsed_items = []
        try:
            for item in json.loads(items_data):
                quantity = int(item['quantity'])
                if quantity < 1:
                    raise ValueError('Quantity must be at least 1.')
                parsed_items.append({
                    'product_id': int(item['product_id']),
                    'quantity': quantity,
                })
        except (ValueError, TypeError, KeyError, AttributeError):
            messages.error(request, 'Invalid items data format.')
            return redirect('inventory:stockout_create')

        if form.is_valid() and parsed_items:
            try:
                with transaction.atomic():
                    stockout = form.save(commit=False)
                    stockout.created_by = request.user
                    stockout.save()

                    # Create stock out items
                    product_ids = [item['product_id'] for item in parsed_items]
                    products_map = {
                        p.id: p for p in Product.objects.filter(id__in=product_ids)
                    }

                    for item in parsed_items:
                        product = products_map.get(item['product_id'])
                        if not product:
                            raise ValueError('A selected product no longer exists.')
                        StockOutItem.objects.create(
                            stockout=stockout,
                            product=product,
                            quantity=item['quantity'],
                            cost_price=product.average_cost
                        )

                    # Complete the stock out immediately. Any failure here rolls
                    # back the header and its items along with the stock changes.
                    stockout.complete_stockout()
                    create_audit_log(request, 'STOCK_OUT', stockout, {
                        'reason': stockout.get_reason_display(),
                        'total_value': str(stockout.total_value),
                        'items_count': len(parsed_items)
                    })
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('inventory:stockout_create')

            messages.success(request, f'Stock out "{stockout.stockout_number}" completed successfully.')
            return redirect('inventory:stockout_detail', pk=stockout.pk)
        else:
            if not parsed_items:
                messages.error(request, 'Please add at least one item.')
    else:
        form = StockOutForm(initial={'stockout_date': timezone.now()})

    context = {
        'form': form,
        'warehouses': warehouses,
        'products': products,
        'reason_choices': StockOut.Reason.choices,
    }
    return render(request, 'inventory/stockout_form.html', context)


@manager_required
def stockout_detail(request, pk):
    """View stock out details."""
    stockout = get_object_or_404(
        StockOut.objects.select_related('warehouse', 'created_by').prefetch_related(
            'items__product'
        ),
        pk=pk
    )
    return render(request, 'inventory/stockout_detail.html', {'stockout': stockout})


@manager_required
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
    
    return redirect('inventory:stockout_detail', pk=pk)


@cashier_required
def api_warehouse_stocks(request, warehouse_id):
    """API endpoint to get available stocks for a warehouse."""
    product_id = request.GET.get('product')
    stocks = ProductStock.objects.filter(warehouse_id=warehouse_id, quantity__gt=0).select_related('product')
    
    if product_id:
        stocks = stocks.filter(product_id=product_id)
    
    # Both product_name and product_sku are emitted because two templates consume
    # this: stockout_form.html reads neither, transfer_form.html reads product_sku.
    data = [{
        'id': s.id,
        'product_id': s.product_id,
        'product_name': s.product.display_name,
        'product_sku': s.product.sku,
        'quantity': s.quantity,
        'average_cost': str(s.product.average_cost),
    } for s in stocks]
    
    return JsonResponse(data, safe=False)
