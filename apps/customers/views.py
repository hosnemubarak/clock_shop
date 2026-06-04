from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.db import transaction
from django.http import JsonResponse
from decimal import Decimal

from .models import Customer, Payment, CustomerNote
from .forms import CustomerForm, PaymentForm, CustomerNoteForm, QuickPaymentForm
from apps.sales.models import Sale
from apps.core.utils import create_audit_log


@login_required
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
    
    paginator = Paginator(customers, 10)
    page = request.GET.get('page')
    customers = paginator.get_page(page)
    
    # Summary stats
    total_due = Customer.objects.aggregate(total=Sum('total_due'))['total'] or Decimal('0')
    
    context = {
        'customers': customers,
        'search': search,
        'total_due': total_due,
    }
    return render(request, 'customers/customer_list.html', context)


@login_required
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
        total_quantity=Sum('quantity'),
        total_amount=Sum('quantity') * Sum('unit_price')
    ).order_by('-total_quantity')[:10]
    
    context = {
        'customer': customer,
        'purchases': purchases,
        'payments': payments,
        'unpaid_invoices': unpaid_invoices,
        'product_summary': product_summary,
    }
    return render(request, 'customers/customer_detail.html', context)


@login_required
def customer_create(request):
    """Create a new customer."""
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            create_audit_log(request, 'CREATE', customer)
            messages.success(request, f'Customer "{customer.name}" created.')
            return redirect('customer_detail', pk=customer.pk)
    else:
        form = CustomerForm()
    
    return render(request, 'customers/customer_form.html', {'form': form, 'title': 'Add Customer'})


@login_required
def customer_edit(request, pk):
    """Edit a customer."""
    customer = get_object_or_404(Customer, pk=pk)
    
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            customer = form.save()
            create_audit_log(request, 'UPDATE', customer)
            messages.success(request, f'Customer "{customer.name}" updated.')
            return redirect('customer_detail', pk=customer.pk)
    else:
        form = CustomerForm(instance=customer)
    
    return render(request, 'customers/customer_form.html', {
        'form': form,
        'title': 'Edit Customer',
        'customer': customer
    })


@login_required
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
    
    return redirect('customer_detail', pk=pk)


@login_required
def customer_statement(request, pk):
    """Generate customer statement."""
    customer = get_object_or_404(Customer, pk=pk)
    
    # Date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Get all transactions
    sales = customer.sales.filter(status='completed')
    payments = customer.payments.all()
    
    if date_from:
        sales = sales.filter(sale_date__date__gte=date_from)
        payments = payments.filter(payment_date__date__gte=date_from)
    if date_to:
        sales = sales.filter(sale_date__date__lte=date_to)
        payments = payments.filter(payment_date__date__lte=date_to)
    
    # Combine and sort transactions
    transactions = []
    for sale in sales:
        transactions.append({
            'date': sale.sale_date,
            'type': 'Invoice',
            'reference': sale.invoice_number,
            'debit': sale.total_amount,
            'credit': Decimal('0'),
        })
    
    for payment in payments:
        transactions.append({
            'date': payment.payment_date,
            'type': 'Payment',
            'reference': payment.reference or f'PMT-{payment.pk}',
            'debit': Decimal('0'),
            'credit': payment.amount,
        })
    
    transactions.sort(key=lambda x: x['date'])
    
    # Calculate running balance
    balance = Decimal('0')
    for t in transactions:
        balance += t['debit'] - t['credit']
        t['balance'] = balance
    
    context = {
        'customer': customer,
        'transactions': transactions,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'customers/customer_statement.html', context)


@login_required
def payment_list(request):
    """List all payments."""
    payments = Payment.objects.select_related('customer', 'sale', 'received_by').all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        payments = payments.filter(
            Q(customer__name__icontains=search) |
            Q(reference__icontains=search) |
            Q(sale__invoice_number__icontains=search)
        )
    
    # Date filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        payments = payments.filter(payment_date__date__gte=date_from)
    if date_to:
        payments = payments.filter(payment_date__date__lte=date_to)
    
    paginator = Paginator(payments, 10)
    page = request.GET.get('page')
    payments = paginator.get_page(page)
    
    context = {
        'payments': payments,
        'search': search,
    }
    return render(request, 'customers/payment_list.html', context)


@login_required
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
            
            # Update customer balance
            payment.customer.total_paid += payment.amount
            payment.customer.total_due -= payment.amount
            payment.customer.save()
            
            # Update sale payment status if linked to specific sale
            if payment.sale:
                payment.sale.paid_amount += payment.amount
                payment.sale.update_payment_status()
            
            create_audit_log(request, 'PAYMENT', payment, {
                'amount': str(payment.amount),
                'customer': payment.customer.name,
                'invoice': payment.sale.invoice_number if payment.sale else 'General'
            })
            
            messages.success(request, f'Payment of {payment.amount} recorded.')
            return redirect('customer_detail', pk=payment.customer.pk)
    else:
        form = PaymentForm(customer=customer)
    
    context = {
        'form': form,
        'customer': customer,
        'unpaid_invoices': unpaid_invoices,
    }
    return render(request, 'customers/payment_form.html', context)


@login_required
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
        'unpaid_invoices': list(unpaid),
    }
    
    return JsonResponse(data)


@login_required
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
