from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.core.decorators import cashier_required, manager_required
from django.contrib import messages
from django.db.models import Case, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
import json
import logging

from .models import Sale, SaleReturn, SaleReturnItem
from .forms import SaleForm, PaymentForm
from apps.inventory.models import Product, ProductStock
from apps.warehouse.models import Warehouse
from apps.customers.models import Customer, Payment
from apps.core.utils import create_audit_log, paginate

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


@cashier_required
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
    
    # Customer filter
    customer_id = request.GET.get('customer')
    if customer_id:
        sales = sales.filter(customer_id=customer_id)
    
    sales = paginate(request, sales, 10)

    customers = Customer.objects.filter(is_active=True).order_by('name')

    context = {
        'sales': sales,
        'search': search,
        'status': status,
        'payment_status': payment_status,
        'date_from': date_from,
        'date_to': date_to,
        'date_filter': date_filter,
        'customer_id': customer_id,
        'customers': customers,
    }
    return render(request, 'sales/sale_list.html', context)


@cashier_required
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


@cashier_required
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


@cashier_required
def sale_cancel(request, pk):
    """Cancel a sale and restore stock."""
    sale = get_object_or_404(Sale, pk=pk)
    
    if request.method == 'POST':
        if sale.status == 'cancelled':
            messages.error(request, 'Sale is already cancelled.')
        elif sale.paid_amount > 0:
            messages.error(request, 'Cannot cancel a sale with payments. Process refund first.')
        elif sale.returns.exists():
            # Returns already restocked some units and adjusted the ledger.
            # Cancelling would restock the full original quantity again, so the
            # returned units would be double-counted. Block it outright.
            messages.error(request, 'Cannot cancel a sale that has returns. Reverse the returns first.')
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


@cashier_required
def sale_payment(request, pk):
    """Record payment for a sale."""
    sale_base = get_object_or_404(Sale, pk=pk)
    
    if request.method == 'POST':
        if sale_base.status == Sale.Status.CANCELLED:
            messages.error(request, 'Cannot record payment for a cancelled sale.')
            return redirect('sales:sale_detail', pk=sale_base.pk)
            
        form = PaymentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            
            if amount > sale_base.due_amount:
                messages.error(request, f'Payment amount exceeds due amount ({sale_base.due_amount}).')
            else:
                with transaction.atomic():
                    # Lock the sale to prevent concurrent payments from overpaying
                    sale = Sale.objects.select_for_update().get(pk=sale_base.pk)
                    if amount > sale.due_amount:
                        messages.error(request, f'Payment amount exceeds due amount ({sale.due_amount}).')
                        return redirect('sales:sale_detail', pk=sale.pk)
                        
                    # Create payment record. The Payment post_save signal
                    # recalculates sale.paid_amount, sale.payment_status and the
                    # customer balance from the persisted payment rows.
                    payment = Payment.objects.create(
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
                    from django.urls import reverse
                    return redirect(reverse('sales:sale_detail', args=[sale_base.pk]) + f'?print_payment={payment.pk}')
        else:
            messages.error(request, 'Invalid payment data.')
    
    return redirect('sales:sale_detail', pk=sale_base.pk)


@cashier_required
def sale_print(request, pk):
    """Print-friendly invoice view."""
    sale = get_object_or_404(
        Sale.objects.select_related('customer', 'created_by').prefetch_related(
            'items__product', 'items__warehouse'
        ),
        pk=pk
    )
    return render(request, 'sales/sale_print.html', {'sale': sale})


@cashier_required
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
            'average_cost': str(p.average_cost),
            'shop_stock': p.shop_stock,
            'total_stock': p.total_stock,
        } for p in rows],
        'query': query,
        'truncated': len(rows) == limit,
    })


@cashier_required
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


# ---------------------------------------------------------------------------
# Sale Returns
# ---------------------------------------------------------------------------

def _returned_quantities(sale):
    """Map of sale_item_id -> total quantity already returned across all returns."""
    rows = SaleReturnItem.objects.filter(
        sale_return__sale=sale
    ).values('sale_item_id').annotate(total=Sum('quantity'))
    return {row['sale_item_id']: row['total'] for row in rows}


@cashier_required
def return_list(request):
    """List sale returns."""
    returns = SaleReturn.objects.select_related('sale', 'created_by').all()

    search = request.GET.get('search', '').strip()
    if search:
        returns = returns.filter(
            Q(return_number__icontains=search) |
            Q(sale__invoice_number__icontains=search)
        )

    returns = paginate(request, returns, 10)
    return render(request, 'sales/return_list.html', {
        'returns': returns,
        'search': search,
    })


@cashier_required
def return_detail(request, pk):
    """View a sale return."""
    sale_return = get_object_or_404(
        SaleReturn.objects.select_related('sale', 'created_by').prefetch_related(
            'items__sale_item__product'
        ),
        pk=pk
    )
    return render(request, 'sales/return_detail.html', {'sale_return': sale_return})


@cashier_required
def return_create(request):
    """Create a sale return against a completed sale and restock the items.

    Requires ``?sale=<id>`` (linked from the sale detail page). Each line's
    returnable quantity is the sold quantity minus what has already been
    returned. Restock and record creation happen in one atomic block.
    """
    sale_id = request.GET.get('sale') or request.POST.get('sale')
    sale = get_object_or_404(
        Sale.objects.prefetch_related('items__product'),
        pk=sale_id
    ) if sale_id else None

    if sale is None:
        messages.error(request, 'Select a sale to return items from.')
        return redirect('sales:sale_list')

    already_returned = _returned_quantities(sale)
    # Annotate each item with its remaining returnable quantity for the template.
    returnable_items = []
    for item in sale.items.all():
        remaining = item.quantity - already_returned.get(item.id, 0)
        if remaining > 0:
            item.returnable = remaining
            returnable_items.append(item)

    if sale.status != Sale.Status.COMPLETED:
        messages.error(request, 'Only completed sales can be returned.')
        return redirect('sales:sale_detail', pk=sale.pk)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        return_date = request.POST.get('return_date') or timezone.now()
        refund_raw = request.POST.get('refund_amount', '0') or '0'

        # Collect requested quantities keyed by sale_item id.
        remaining_map = {item.id: item.returnable for item in returnable_items}
        requested = {}
        for item in returnable_items:
            raw = request.POST.get(f'qty_{item.id}', '').strip()
            if not raw:
                continue
            try:
                qty = int(raw)
            except ValueError:
                messages.error(request, 'Invalid quantity entered.')
                return redirect(f"{request.path}?sale={sale.pk}")
            if qty <= 0:
                continue
            if qty > remaining_map[item.id]:
                messages.error(
                    request,
                    f'Cannot return {qty} of "{item}" (only {remaining_map[item.id]} returnable).'
                )
                return redirect(f"{request.path}?sale={sale.pk}")
            requested[item.id] = qty

        if not reason:
            messages.error(request, 'Please provide a reason for the return.')
            return redirect(f"{request.path}?sale={sale.pk}")

        if not requested:
            messages.error(request, 'Enter a quantity for at least one item to return.')
            return redirect(f"{request.path}?sale={sale.pk}")

        from decimal import Decimal, InvalidOperation
        try:
            refund_amount = Decimal(str(refund_raw))
            if refund_amount < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid refund amount.')
            return redirect(f"{request.path}?sale={sale.pk}")

        # Calculate value of returned goods to cap the refund
        returned_goods_value = Decimal('0.00')
        for item in returnable_items:
            qty = requested.get(item.id)
            if qty:
                # Apportion the line discount proportionally
                if item.quantity > 0:
                    gross = (item.quantity * item.unit_price) - item.discount
                    per_unit_net = (gross / item.quantity)
                    returned_goods_value += (per_unit_net * qty).quantize(Decimal('0.01'))
                    
        if refund_amount > sale.paid_amount:
            messages.error(request, f'Refund amount cannot exceed the paid amount ({sale.paid_amount}).')
            return redirect(f"{request.path}?sale={sale.pk}")
            
        if refund_amount > returned_goods_value:
            messages.error(request, f'Refund amount cannot exceed the value of the returned goods ({returned_goods_value}).')
            return redirect(f"{request.path}?sale={sale.pk}")

        with transaction.atomic():
            sale_return = SaleReturn.objects.create(
                sale=sale,
                return_date=return_date,
                reason=reason,
                refund_amount=refund_amount,
                created_by=request.user,
            )
            for sale_item_id, qty in requested.items():
                SaleReturnItem.objects.create(
                    sale_return=sale_return,
                    sale_item_id=sale_item_id,
                    quantity=qty,
                )
            # Restock the returned units (locks stock rows).
            sale_return.restock_items()
            # Move the money: reduce the sale total by returned goods value and
            # the paid amount by the refund, then recompute the customer balance.
            sale_return.reconcile_sale_ledger()

            create_audit_log(request, 'SALE', sale_return, {
                'action': 'return',
                'sale': sale.invoice_number,
                'refund': str(refund_amount),
                'items': len(requested),
            })

        messages.success(request, f'Return "{sale_return.return_number}" recorded and stock restored.')
        return redirect('sales:return_detail', pk=sale_return.pk)

    return render(request, 'sales/return_form.html', {
        'sale': sale,
        'returnable_items': returnable_items,
    })
