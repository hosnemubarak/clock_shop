from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.contrib import messages
from django.db.models import Sum, Count, F
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal
from django.contrib.auth import views as auth_views
from django.conf import settings
from .utils import verify_recaptcha, get_client_ip

from .models import AuditLog, SystemSettings
from .forms import SystemSettingsForm
from apps.inventory.models import Product, Batch
from apps.sales.models import Sale, SaleItem, SaleReturn, SaleReturnItem
from apps.customers.models import Customer
from apps.warehouse.models import Warehouse


class CustomLoginView(auth_views.LoginView):
    """Custom Login View with reCAPTCHA verification."""
    def post(self, request, *args, **kwargs):
        if getattr(settings, 'RECAPTCHA_ENABLED', False):
            token = request.POST.get('recaptcha_token')
            if not verify_recaptcha(token, get_client_ip(request)):
                form = self.get_form()
                form.add_error(None, "reCAPTCHA verification failed. Please try again.")
                return self.form_invalid(form)
        return super().post(request, *args, **kwargs)


@login_required
def dashboard(request):
    """Main dashboard view with key metrics."""
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    is_admin = request.user.is_staff or request.user.is_superuser
    
    # Base querysets
    sales_qs = Sale.objects.filter(status='completed')
    returns_qs = SaleReturn.objects.all()
    recent_sales_qs = Sale.objects.select_related('customer')
    
    if not is_admin:
        sales_qs = sales_qs.filter(created_by=request.user)
        returns_qs = returns_qs.filter(sale__created_by=request.user)
        recent_sales_qs = recent_sales_qs.filter(created_by=request.user)
        
    # Sales metrics
    gross_sales_today = sales_qs.filter(
        sale_date__date=today
    ).aggregate(total=Sum(F('subtotal') - F('discount_amount')))['total'] or Decimal('0')
    
    returns_today = returns_qs.filter(
        return_date__date=today
    ).aggregate(total=Sum('refund_amount'))['total'] or Decimal('0')
    
    total_sales_today = gross_sales_today - returns_today
    
    gross_sales_month = sales_qs.filter(
        sale_date__date__gte=month_start
    ).aggregate(total=Sum(F('subtotal') - F('discount_amount')))['total'] or Decimal('0')
    
    returns_month = returns_qs.filter(
        return_date__date__gte=month_start
    ).aggregate(total=Sum('refund_amount'))['total'] or Decimal('0')
    
    total_sales_month = gross_sales_month - returns_month
    
    # Profit calculation
    if is_admin:
        sales_month_agg = sales_qs.filter(
            sale_date__date__gte=month_start
        ).aggregate(
            net_sales=Sum(F('subtotal') - F('discount_amount')),
            total_cost=Sum('total_cost')
        )
        net_sales = sales_month_agg['net_sales'] or Decimal('0.00')
        total_cost = sales_month_agg['total_cost'] or Decimal('0.00')
        gross_profit_month = net_sales - total_cost
        
        # Returned items profit for the month
        returned_items_month = SaleReturnItem.objects.filter(
            sale_return__return_date__date__gte=month_start
        ).select_related('sale_item')
        
        returns_profit_month = Decimal('0')
        for item in returned_items_month:
            effective_unit_price = item.sale_item.unit_price - (item.sale_item.discount / Decimal(item.sale_item.quantity))
            item_refund_total = Decimal(item.quantity) * effective_unit_price
            item_cost_total = Decimal(item.quantity) * item.sale_item.cost_price
            returns_profit_month += item_refund_total - item_cost_total
            
        profit_month = gross_profit_month - returns_profit_month
    else:
        profit_month = Decimal('0')
    
    # Inventory metrics
    total_products = Product.objects.filter(is_active=True).count() if is_admin else 0

    total_product_quantity = Batch.objects.filter(
        quantity__gt=0
    ).aggregate(total=Sum('quantity'))['total'] or 0 if is_admin else 0
    
    # Get low stock threshold from settings
    from .models import SystemSettings
    db_settings = SystemSettings.get_settings()
    low_stock_threshold = db_settings.low_stock_threshold or 5
    
    low_stock_products = Batch.objects.filter(
        quantity__gt=0,
        quantity__lte=low_stock_threshold
    ).values('product').distinct().count() if is_admin else 0
    
    # Customer metrics
    total_customers = Customer.objects.count()
    total_dues = Customer.objects.aggregate(
        total=Sum('total_due')
    )['total'] or Decimal('0.00') if is_admin else Decimal('0.00')
    
    # Warehouse metrics
    total_warehouses = Warehouse.objects.filter(is_active=True).count() if is_admin else 0
    
    # Recent sales
    recent_sales = recent_sales_qs.order_by('-sale_date')[:10]
    
    # Low stock alerts
    low_stock_batches = Batch.objects.filter(
        quantity__gt=0,
        quantity__lte=low_stock_threshold
    ).select_related('product', 'warehouse').order_by('quantity')[:10] if is_admin else []
    
    # Payment status counts for chart
    chart_sales = Sale.objects.all()
    if not is_admin:
        chart_sales = chart_sales.filter(created_by=request.user)
    payment_status_counts = chart_sales.values('payment_status').annotate(
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
        'total_product_quantity': total_product_quantity,
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


@staff_member_required
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
        
        # reCAPTCHA Validation
        if getattr(settings, 'RECAPTCHA_ENABLED', False):
            token = request.POST.get('recaptcha_token')
            if not verify_recaptcha(token, get_client_ip(request)):
                errors.append('reCAPTCHA verification failed. Please try again.')
        
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


def is_superuser(user):
    """Check if user is superuser."""
    return user.is_superuser


@login_required
@user_passes_test(is_superuser)
def system_settings(request):
    """View and update system settings."""
    settings = SystemSettings.get_settings()
    
    if request.method == 'POST':
        form = SystemSettingsForm(request.POST, request.FILES, instance=settings)
        if form.is_valid():
            settings = form.save(commit=False)
            settings.updated_by = request.user
            settings.save()
            messages.success(request, 'System settings updated successfully.')
            return redirect('system_settings')
    else:
        form = SystemSettingsForm(instance=settings)
    
    context = {
        'form': form,
        'settings': settings,
    }
    return render(request, 'core/system_settings.html', context)
