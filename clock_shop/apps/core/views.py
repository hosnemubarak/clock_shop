from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.contrib import messages
from django.db.models import Sum, Count, F
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import AuditLog
from apps.inventory.models import Product, Batch
from apps.sales.models import Sale, SaleItem
from apps.customers.models import Customer
from apps.warehouse.models import Warehouse


@login_required
def dashboard(request):
    """Main dashboard view with key metrics."""
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    # Sales metrics
    total_sales_today = Sale.objects.filter(
        sale_date__date=today
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    
    total_sales_month = Sale.objects.filter(
        sale_date__date__gte=month_start
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    
    # Profit calculation
    profit_month = SaleItem.objects.filter(
        sale__sale_date__date__gte=month_start
    ).aggregate(
        profit=Sum(F('quantity') * (F('unit_price') - F('cost_price')))
    )['profit'] or Decimal('0')
    
    # Inventory metrics
    total_products = Product.objects.filter(is_active=True).count()
    
    low_stock_products = Batch.objects.filter(
        quantity__gt=0,
        quantity__lte=10
    ).values('product').distinct().count()
    
    # Customer metrics
    total_customers = Customer.objects.count()
    total_dues = Customer.objects.aggregate(
        total=Sum('total_due')
    )['total'] or Decimal('0.00')
    
    # Warehouse metrics
    total_warehouses = Warehouse.objects.filter(is_active=True).count()
    
    # Recent sales
    recent_sales = Sale.objects.select_related('customer').order_by('-sale_date')[:10]
    
    # Low stock alerts
    low_stock_batches = Batch.objects.filter(
        quantity__gt=0,
        quantity__lte=10
    ).select_related('product', 'warehouse').order_by('quantity')[:10]
    
    # Payment status counts for chart
    payment_status_counts = Sale.objects.values('payment_status').annotate(
        count=Count('id')
    )
    paid_count = 0
    partial_count = 0
    unpaid_count = 0
    for status in payment_status_counts:
        if status['payment_status'] == 'paid':
            paid_count = status['count']
        elif status['payment_status'] == 'partial':
            partial_count = status['count']
        elif status['payment_status'] == 'unpaid':
            unpaid_count = status['count']
    
    context = {
        'total_sales_today': total_sales_today,
        'total_sales_month': total_sales_month,
        'profit_month': profit_month,
        'total_products': total_products,
        'low_stock_products': low_stock_products,
        'total_customers': total_customers,
        'total_dues': total_dues,
        'total_warehouses': total_warehouses,
        'recent_sales': recent_sales,
        'low_stock_batches': low_stock_batches,
        'paid_count': paid_count,
        'partial_count': partial_count,
        'unpaid_count': unpaid_count,
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def audit_logs(request):
    """View audit logs."""
    from django.core.paginator import Paginator
    from django.db.models import Q
    
    logs = AuditLog.objects.select_related('user').all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        logs = logs.filter(
            Q(action__icontains=search) |
            Q(model_name__icontains=search) |
            Q(object_repr__icontains=search)
        )
    
    # Action filter
    action_filter = request.GET.get('action')
    if action_filter:
        logs = logs.filter(action=action_filter)
    
    # User filter
    user_filter = request.GET.get('user')
    if user_filter:
        logs = logs.filter(user_id=user_filter)
    
    # Get all users for filter dropdown
    users = User.objects.filter(auditlog__isnull=False).distinct().order_by('username')
    
    paginator = Paginator(logs, 20)
    page = request.GET.get('page')
    logs = paginator.get_page(page)
    
    context = {
        'logs': logs,
        'search': search,
        'users': users,
        'selected_action': action_filter or '',
        'selected_user': user_filter or '',
    }
    return render(request, 'core/audit_logs.html', context)


def register(request):
    """User registration view."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        errors = []
        
        # Validation
        if not username:
            errors.append('Username is required.')
        elif User.objects.filter(username=username).exists():
            errors.append('Username already exists.')
        
        if not email:
            errors.append('Email is required.')
        elif User.objects.filter(email=email).exists():
            errors.append('Email already registered.')
        
        if not password1:
            errors.append('Password is required.')
        elif len(password1) < 8:
            errors.append('Password must be at least 8 characters.')
        elif password1 != password2:
            errors.append('Passwords do not match.')
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'core/register.html', {
                'form': {
                    'username': {'value': username},
                    'email': {'value': email},
                    'first_name': {'value': first_name},
                    'last_name': {'value': last_name},
                }
            })
        
        # Create user (inactive until admin approves)
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=first_name,
            last_name=last_name
        )
        user.is_active = False
        user.save()
        
        messages.success(request, 'Your account has been created successfully! Please wait for admin approval before you can login.')
        return redirect('login')
    
    return render(request, 'core/register.html')
