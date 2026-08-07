from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Value, Case, When, IntegerField
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import json
import logging

from apps.core.decorators import has_permission
from apps.core.utils import create_audit_log, paginate
from apps.inventory.models import Product
from apps.warehouse.models import Warehouse
from .models import Quotation, QuotationItem

logger = logging.getLogger(__name__)

PRODUCT_SEARCH_LIMIT = 25


def _to_int_or(value, fallback):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


@has_permission('quotations.view_quotation')
def quotation_list(request):
    """List all quotations with filtering."""
    quotations = Quotation.objects.select_related('created_by').all()

    search = request.GET.get('search', '')
    if search:
        quotations = quotations.filter(
            Q(quotation_number__icontains=search) |
            Q(title__icontains=search) |
            Q(client_name__icontains=search)
        )

    status = request.GET.get('status')
    if status:
        quotations = quotations.filter(status=status)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        quotations = quotations.filter(quotation_date__gte=date_from)
    if date_to:
        quotations = quotations.filter(quotation_date__lte=date_to)

    date_filter = request.GET.get('date_filter')
    if date_filter == 'today':
        today = timezone.localtime().date()
        quotations = quotations.filter(quotation_date=today)
        date_from = today.strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')
    elif date_filter == 'this_month':
        today = timezone.localtime().date()
        start_of_month = today.replace(day=1)
        quotations = quotations.filter(quotation_date__range=(start_of_month, today))
        date_from = start_of_month.strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')

    quotations = paginate(request, quotations, 25)

    context = {
        'quotations': quotations,
        'search': search,
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'date_filter': date_filter,
    }
    return render(request, 'quotations/quotation_list.html', context)


@has_permission('quotations.add_quotation')
def quotation_create(request):
    """Render the quotation creation screen."""
    context = {
        'today': timezone.localdate().isoformat(),
    }
    return render(request, 'quotations/quotation_form.html', context)


@has_permission('quotations.view_quotation')
def quotation_detail(request, pk):
    """View quotation details."""
    quotation = get_object_or_404(
        Quotation.objects.select_related('created_by').prefetch_related(
            'items__product'
        ),
        pk=pk
    )
    context = {'quotation': quotation}
    return render(request, 'quotations/quotation_detail.html', context)


@has_permission('quotations.view_quotation')
def quotation_print(request, pk):
    """Print-friendly quotation view."""
    quotation = get_object_or_404(
        Quotation.objects.prefetch_related('items__product'),
        pk=pk
    )
    return render(request, 'quotations/quotation_print.html', {'quotation': quotation})


@has_permission('quotations.delete_quotation')
def quotation_delete(request, pk):
    """Delete a quotation."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if request.method == 'POST':
        qtn_num = quotation.quotation_number
        create_audit_log(request, 'DELETE', quotation)
        quotation.delete()
        messages.success(request, f'Quotation "{qtn_num}" deleted.')
    return redirect('quotations:quotation_list')


@has_permission('quotations.add_quotation')
@transaction.atomic
def api_quotation_save(request):
    """API endpoint to save a quotation from JSON. No stock impact."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        try:
            data = json.loads(request.body)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

        title = (data.get('title') or '').strip()
        if not title:
            return JsonResponse({'status': 'error', 'message': 'Quotation title is required.'}, status=400)

        items = data.get('items', [])
        if not items:
            return JsonResponse({'status': 'error', 'message': 'At least one item is required.'}, status=400)

        quotation_date = data.get('quotation_date') or timezone.localdate().isoformat()
        valid_until = data.get('valid_until') or None

        discount_raw = data.get('discount', '0')
        try:
            discount_amount = Decimal(str(discount_raw))
            if discount_amount < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            discount_amount = Decimal('0.00')

        quotation = Quotation.objects.create(
            title=title,
            quotation_date=quotation_date,
            valid_until=valid_until,
            client_name=(data.get('client_name') or '').strip(),
            client_phone=(data.get('client_phone') or '').strip(),
            client_address=(data.get('client_address') or '').strip(),
            discount_amount=discount_amount,
            notes=(data.get('notes') or '').strip(),
            created_by=request.user,
        )

        subtotal = Decimal('0.00')
        for item_data in items:
            is_custom = item_data.get('is_custom', False)
            product_id = item_data.get('product_id')
            product = None

            if not is_custom and product_id:
                try:
                    product = Product.objects.get(pk=product_id)
                except Product.DoesNotExist:
                    pass

            try:
                quantity = int(item_data.get('quantity', 1))
                if quantity <= 0:
                    quantity = 1
            except (ValueError, TypeError):
                quantity = 1

            try:
                unit_price = Decimal(str(item_data.get('unit_price', '0')))
            except (InvalidOperation, ValueError):
                unit_price = Decimal('0.00')

            try:
                item_discount = Decimal(str(item_data.get('discount', '0')))
                if item_discount < 0:
                    item_discount = Decimal('0.00')
            except (InvalidOperation, ValueError):
                item_discount = Decimal('0.00')

            qi = QuotationItem.objects.create(
                quotation=quotation,
                product=product,
                is_custom=is_custom,
                custom_description=(item_data.get('custom_description') or '').strip(),
                quantity=quantity,
                unit_price=unit_price,
                discount=item_discount,
            )
            subtotal += qi.total_price

        quotation.subtotal = subtotal
        quotation.total_amount = subtotal - discount_amount
        quotation.save(update_fields=['subtotal', 'total_amount'])

        create_audit_log(request, 'CREATE', quotation, {
            'action': 'quotation_created',
            'total': str(quotation.total_amount),
        })

        return JsonResponse({
            'status': 'success',
            'quotation_id': quotation.id,
            'quotation_number': quotation.quotation_number,
            'message': 'Quotation saved successfully.'
        })

    except Exception:
        logger.exception('Quotation save failed')
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)


@has_permission('inventory.view_product')
def api_product_search(request):
    """Search products for the quotation screen. Display only — no stock impact."""
    query = (request.GET.get('q') or '').strip()

    products = Product.objects.filter(is_active=True).select_related('brand', 'category')

    if query:
        products = products.filter(
            Q(sku__icontains=query)
            | Q(brand__name__icontains=query)
            | Q(category__name__icontains=query)
        )

    # Exact SKU match first for barcode scanning
    exact_first = Case(
        When(sku__iexact=query, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    ) if query else Value(1, output_field=IntegerField())

    products = products.order_by(exact_first, 'sku')

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
        } for p in rows],
        'query': query,
        'truncated': len(rows) == limit,
    })
