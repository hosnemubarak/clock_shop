import json
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.core.decorators import has_permission
from django.contrib import messages
from django.db.models import Q, Sum, F
from django.db import transaction, IntegrityError
from django.http import JsonResponse
from django.utils import timezone
from decimal import Decimal

from .models import Customer, Payment, CustomerNote
from .forms import CustomerForm, OpeningBalanceForm, PaymentForm, CustomerNoteForm
from apps.sales.models import Sale, SaleReturn
from apps.core.utils import create_audit_log, paginate

logger = logging.getLogger(__name__)


@has_permission('customers.view_customer')
def customer_list(request):
    """List all customers with filtering."""
    customers = Customer.objects.all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        customers = customers.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(email__icontains=search)
        )
    
    # Due filter
    due_filter = request.GET.get('due')
    if due_filter == 'has_due':
        customers = customers.filter(total_due__gt=0)
    elif due_filter == 'no_due':
        customers = customers.filter(total_due__lte=0)
    
    # Status filter
    status = request.GET.get('status')
    if status == 'active':
        customers = customers.filter(is_active=True)
    elif status == 'inactive':
        customers = customers.filter(is_active=False)
    
    customers = paginate(request, customers, 25)

    # Summary stats
    summary = Customer.objects.aggregate(
        total_due=Sum('total_due'),
        total_purchases=Sum('total_purchases')
    )
    total_due = summary['total_due'] or Decimal('0')
    total_purchases = summary['total_purchases'] or Decimal('0')
    total_customers = Customer.objects.count()
    
    context = {
        'customers': customers,
        'search': search,
        'total_due': total_due,
        'total_purchases': total_purchases,
        'total_customers': total_customers,
    }
    return render(request, 'customers/customer_list.html', context)


@has_permission('customers.view_customer')
def customer_detail(request, pk):
    """View customer details with purchase and payment history."""
    customer = get_object_or_404(Customer, pk=pk)
    
    # Purchase history
    purchases = customer.get_purchase_history()[:20]
    
    # Payment history
    payments = customer.get_payment_history()[:20]
    
    # Unpaid invoices
    unpaid_invoices = customer.get_unpaid_invoices()
    
    # Purchase summary
    from apps.sales.models import SaleItem
    product_summary = SaleItem.objects.filter(
        sale__customer=customer,
        sale__status='completed'
    ).values(
        'product__sku', 'product__brand__name'
    ).annotate(
        total_quantity=Sum(F('quantity') - F('returned_quantity')),
        total_amount=Sum((F('quantity') - F('returned_quantity')) * F('unit_price'))
    ).order_by('-total_quantity')[:10]
    
    context = {
        'customer': customer,
        'purchases': purchases,
        'payments': payments,
        'unpaid_invoices': unpaid_invoices,
        'product_summary': product_summary,
        'opening_balance_form': OpeningBalanceForm(instance=customer),
    }
    return render(request, 'customers/customer_detail.html', context)


@has_permission('customers.add_customer')
def customer_create(request):
    """Create a new customer."""
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            create_audit_log(request, 'CREATE', customer)
            messages.success(request, f'Customer "{customer.name}" created.')
            return redirect('customers:customer_detail', pk=customer.pk)
    else:
        form = CustomerForm()
    
    return render(request, 'customers/customer_form.html', {'form': form, 'title': 'Add Customer'})


@has_permission('customers.change_customer')
def customer_edit(request, pk):
    """Edit a customer."""
    customer = get_object_or_404(Customer, pk=pk)
    
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            customer = form.save()
            create_audit_log(request, 'UPDATE', customer)
            messages.success(request, f'Customer "{customer.name}" updated.')
            return redirect('customers:customer_detail', pk=customer.pk)
    else:
        form = CustomerForm(instance=customer)
    
    return render(request, 'customers/customer_form.html', {
        'form': form,
        'title': 'Edit Customer',
        'customer': customer
    })


@has_permission(
    'customers.set_opening_balance',
    json_for_ajax=True,
    json_message='You do not have permission to change opening balances.',
)
def opening_balance_set(request, pk):
    """Set or amend a customer's pre-system outstanding debt."""
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.content_type == 'application/json'
    )
    if request.method == 'POST':
        with transaction.atomic():
            customer = get_object_or_404(
                Customer.objects.select_for_update(),
                pk=pk,
            )
            old_amount = customer.opening_balance
            old_date = customer.opening_balance_date
            form = OpeningBalanceForm(request.POST, instance=customer)
            if form.is_valid():
                customer = form.save()
                customer.recalculate_balance()
                create_audit_log(request, 'UPDATE', customer, {
                    'opening_balance': {
                        'old': str(old_amount),
                        'new': str(customer.opening_balance),
                    },
                    'opening_balance_date': {
                        'old': old_date.isoformat(),
                        'new': customer.opening_balance_date.isoformat(),
                    },
                })
                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'customer_id': customer.pk,
                        'opening_balance': str(customer.opening_balance),
                        'opening_balance_date': customer.opening_balance_date.isoformat(),
                        'total_due': str(customer.total_due),
                    })
                messages.success(request, f'Opening balance for "{customer.name}" updated.')
                return redirect('customers:customer_detail', pk=customer.pk)
    else:
        customer = get_object_or_404(Customer, pk=pk)
        form = OpeningBalanceForm(instance=customer)

    if is_ajax and request.method == 'POST':
        return JsonResponse({
            'status': 'error',
            'errors': {
                field: [str(error) for error in errors]
                for field, errors in form.errors.items()
            },
        }, status=400)

    return render(request, 'customers/opening_balance_form.html', {
        'customer': customer,
        'form': form,
    })


@has_permission('customers.change_customer')
def customer_add_note(request, pk):
    """Add a note to a customer."""
    customer = get_object_or_404(Customer, pk=pk)
    
    if request.method == 'POST':
        form = CustomerNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.customer = customer
            note.created_by = request.user
            note.save()
            messages.success(request, 'Note added.')
    
    return redirect('customers:customer_detail', pk=pk)


@has_permission('customers.view_customer')
def customer_statement(request, pk):
    """Generate customer statement."""
    customer = get_object_or_404(Customer, pk=pk)
    
    # Date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Get all persisted transactions in the requested window.
    sales = customer.sales.filter(status='completed')
    payments = customer.payments.all()
    returns = SaleReturn.objects.filter(
        sale__customer=customer,
        sale__status='completed',
    )
    
    if date_from:
        sales = sales.filter(sale_date__gte=date_from)
        payments = payments.filter(payment_date__date__gte=date_from)
        returns = returns.filter(return_date__date__gte=date_from)
    if date_to:
        sales = sales.filter(sale_date__lte=date_to)
        payments = payments.filter(payment_date__date__lte=date_to)
        returns = returns.filter(return_date__date__lte=date_to)
    
    # Opening balance: everything before the reporting window, so the running
    # balance carries forward instead of restarting at zero.
    opening_balance = Decimal('0')
    if date_from:
        prior_sales = customer.sales.filter(
            status='completed', sale_date__lt=date_from
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        prior_payments = customer.payments.filter(
            payment_date__date__lt=date_from
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        prior_refunds = SaleReturn.objects.filter(
            sale__customer=customer,
            sale__status='completed',
            return_date__date__lt=date_from,
        ).aggregate(total=Sum('refund_amount'))['total'] or Decimal('0')
        persistent_opening = (
            customer.opening_balance
            if customer.opening_balance_date.isoformat() < date_from
            else Decimal('0')
        )
        opening_balance = persistent_opening + prior_sales + prior_refunds - prior_payments

    # Combine and sort transactions
    transactions = []
    opening_in_window = (
        (not date_from or customer.opening_balance_date.isoformat() >= date_from)
        and (not date_to or customer.opening_balance_date.isoformat() <= date_to)
    )
    if opening_in_window and customer.opening_balance > 0:
        transactions.append({
            'date': customer.opening_balance_date,
            'type': 'Opening Balance',
            'reference': 'Opening Balance',
            'debit': customer.opening_balance,
            'credit': Decimal('0'),
            'sort_order': 0,
            'pk': customer.pk,
        })

    for sale in sales:
        transactions.append({
            'date': sale.sale_date,
            'type': 'Invoice',
            'reference': sale.invoice_number,
            'debit': sale.total_amount,
            'credit': Decimal('0'),
            'sort_order': 1,
            'pk': sale.pk,
        })

    for sale_return in returns:
        transactions.append({
            'date': timezone.localtime(sale_return.return_date).date(),
            'type': 'Refund',
            'reference': sale_return.return_number,
            'debit': sale_return.refund_amount,
            'credit': Decimal('0'),
            'sort_order': 2,
            'pk': sale_return.pk,
        })

    for payment in payments:
        transactions.append({
            'date': timezone.localtime(payment.payment_date).date(),
            'type': 'Payment',
            'reference': payment.reference or f'PMT-{payment.pk}',
            'debit': Decimal('0'),
            'credit': payment.amount,
            'sort_order': 3,
            'pk': payment.pk,
        })

    # sale_date is a date and payment_date a datetime; both are normalised to
    # dates above so they are mutually comparable.
    transactions.sort(key=lambda x: (x['date'], x['sort_order'], x['pk']))

    # Calculate running balance
    balance = opening_balance
    for t in transactions:
        balance += t['debit'] - t['credit']
        t['balance'] = balance

    context = {
        'customer': customer,
        'transactions': transactions,
        'opening_balance': opening_balance,
        'closing_balance': balance,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'customers/customer_statement.html', context)


@has_permission('customers.view_payment')
def payment_list(request):
    """List all payments (both general and sale-linked)."""
    payments = Payment.objects.select_related('customer', 'sale', 'received_by').all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        search_query = search.strip()
        payment_id_match = None
        if search_query.upper().startswith('PMT-') and search_query[4:].isdigit():
            payment_id_match = int(search_query[4:])
        elif search_query.isdigit():
            payment_id_match = int(search_query)

        if payment_id_match:
            payments = payments.filter(
                Q(pk=payment_id_match) |
                Q(customer__name__icontains=search_query) |
                Q(reference__icontains=search_query)
            )
        else:
            payments = payments.filter(
                Q(customer__name__icontains=search_query) |
                Q(reference__icontains=search_query)
            )
    
    # Date filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        payments = payments.filter(payment_date__date__gte=date_from)
    if date_to:
        payments = payments.filter(payment_date__date__lte=date_to)

    # Customer filter
    customer_id = request.GET.get('customer')
    if customer_id:
        payments = payments.filter(customer_id=customer_id)
        
    payments = paginate(request, payments, 25)

    customers = Customer.objects.filter(is_active=True).order_by('name')

    context = {
        'payments': payments,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'customer_id': customer_id,
        'customers': customers,
    }
    return render(request, 'customers/payment_list.html', context)


@has_permission('customers.add_payment')
@transaction.atomic
def payment_create(request):
    """Record a new payment."""
    customer_id = request.GET.get('customer')
    customer = None
    unpaid_invoices = []
    
    if customer_id:
        customer = get_object_or_404(Customer, pk=customer_id)
        unpaid_invoices = Sale.objects.filter(
            customer=customer,
            status='completed'
        ).exclude(payment_status='paid').order_by('-sale_date')
    
    if request.method == 'POST':
        form = PaymentForm(request.POST, customer=customer)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.received_by = request.user
            payment.save()
            # The Payment post_save signal recalculates the linked sale's
            # paid_amount/payment_status and the customer balance from the
            # persisted payment rows.

            create_audit_log(request, 'PAYMENT', payment, {
                'amount': str(payment.amount),
                'customer': payment.customer.name if payment.customer else 'Walk-in',
                'invoice': payment.sale.invoice_number if payment.sale else 'General'
            })
            
            messages.success(request, f'Payment of {payment.amount} recorded.')
            from django.urls import reverse
            if payment.customer:
                return redirect(reverse('customers:customer_detail', args=[payment.customer.pk]) + f'?print_payment={payment.pk}')
            else:
                return redirect(reverse('customers:payment_list') + f'?print_payment={payment.pk}')
    else:
        form = PaymentForm(customer=customer)
    
    context = {
        'form': form,
        'customer': customer,
        'unpaid_invoices': unpaid_invoices,
        'has_customers': Customer.objects.exists()
    }
    return render(request, 'customers/payment_form.html', context)


@has_permission('customers.view_customer')
def api_customer_info(request, customer_id):
    """API endpoint to get customer info."""
    customer = get_object_or_404(Customer, pk=customer_id)
    
    # Get unpaid invoices
    unpaid = Sale.objects.filter(
        customer=customer,
        status='completed'
    ).exclude(payment_status='paid').values(
        'id', 'invoice_number', 'total_amount', 'paid_amount', 'sale_date'
    )
    
    data = {
        'id': customer.id,
        'name': customer.name,
        'phone': customer.phone,
        'email': customer.email,
        'total_purchases': str(customer.total_purchases),
        'total_paid': str(customer.total_paid),
        'total_due': str(customer.total_due),
        'opening_balance': str(customer.opening_balance),
        'opening_balance_date': customer.opening_balance_date.isoformat(),
        'unpaid_invoices': list(unpaid),
    }

    loyalty = _customer_loyalty(customer)
    if loyalty:
        data['loyalty'] = loyalty

    return JsonResponse(data)


@has_permission('customers.view_customer')
def api_customer_search(request):
    """API endpoint to search customers dynamically."""
    query = request.GET.get('q', '').strip()
    
    customers = Customer.objects.filter(is_active=True)
    if query:
        customers = customers.filter(
            Q(name__icontains=query) |
            Q(phone__icontains=query) |
            Q(email__icontains=query)
        )
        
    # Limit results to keep it fast
    customers = customers[:20]
    
    data = [{
        'id': c.id,
        'name': c.name,
        'phone': c.phone or '',
    } for c in customers]
    
    return JsonResponse({'results': data})


def _customer_loyalty(customer):
    """Loyalty payload for the sale screen, or None when the shop has no scheme.

    Customer carries no loyalty column today, so this reads whatever a future
    migration adds rather than guessing a tier from spend -- inventing
    thresholds here would put a number on screen the shop never agreed to.
    Add `loyalty_tier` and/or `loyalty_points` to Customer and this starts
    populating on its own; the template and JS already handle the payload.
    """
    tier = getattr(customer, 'loyalty_tier', None)
    points = getattr(customer, 'loyalty_points', None)

    payload = {}
    if tier:
        payload['tier'] = str(tier)
    if points is not None:
        payload['points'] = str(points)

    return payload or None


@has_permission('customers.view_payment')
def payment_print(request, pk):
    """Print-friendly payment receipt view."""
    payment = get_object_or_404(
        Payment.objects.select_related('customer', 'sale', 'received_by'),
        pk=pk
    )
    return render(request, 'customers/payment_print.html', {'payment': payment})


@has_permission('customers.view_customer')
def api_customer_sales(request, customer_id):
    """API endpoint to get customer's unpaid sales."""
    customer = get_object_or_404(Customer, pk=customer_id)
    
    sales = Sale.objects.filter(
        customer=customer,
        status='completed'
    ).exclude(payment_status='paid')
    
    data = [{
        'id': s.id,
        'invoice_number': s.invoice_number,
        'total_amount': str(s.total_amount),
        'paid_amount': str(s.paid_amount),
        'due_amount': str(s.due_amount),
        'sale_date': s.sale_date.strftime('%Y-%m-%d'),
    } for s in sales]
    
    return JsonResponse(data, safe=False)


@has_permission('customers.add_customer')
def api_customer_create(request):
    """API endpoint to create a customer inline."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            phone = data.get('phone', '').strip()
            
            if not name:
                return JsonResponse({'status': 'error', 'message': 'Customer name is required.'}, status=400)

            if not phone:
                return JsonResponse({'status': 'error', 'message': 'Customer phone number is required.'}, status=400)
                
            import re
            if not re.match(r'^(?:\+?88)?01[3-9]\d{8}$', phone):
                return JsonResponse({'status': 'error', 'message': 'Enter a valid Bangladeshi mobile number (e.g. 01712345678).'}, status=400)
                
            credit_limit = data.get('credit_limit', '').strip()
            
            customer_data = {
                'name': name,
                'phone': phone,
                'email': data.get('email', '').strip(),
                'address': data.get('address', '').strip(),
                'notes': data.get('notes', '').strip()
            }
            
            if credit_limit:
                try:
                    customer_data['credit_limit'] = Decimal(credit_limit)
                except:
                    return JsonResponse({'status': 'error', 'message': 'Invalid credit limit format.'}, status=400)
            
            customer = Customer.objects.create(**customer_data)
            
            create_audit_log(request, 'CUSTOMER', customer, {
                'action': 'inline_create',
                'name': name
            })
            
            return JsonResponse({
                'status': 'success',
                'customer': {
                    'id': customer.id,
                    'name': customer.name,
                    'phone': customer.phone
                }
            })
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
        except IntegrityError as e:
            error_msg = str(e)
            if 'email' in error_msg.lower():
                message = "A customer with this email already exists."
            elif 'phone' in error_msg.lower():
                message = "A customer with this phone number already exists."
            else:
                message = "A customer with this information already exists."
            return JsonResponse({'status': 'error', 'message': message}, status=400)
        except Exception:
            logger.exception('Inline customer creation failed')
            return JsonResponse(
                {'status': 'error', 'message': 'Could not create the customer.'},
                status=500,
            )
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
