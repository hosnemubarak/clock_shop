from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from apps.core.decorators import has_permission
from django.contrib.auth.models import User, Group
from django.contrib.auth import login
from django.contrib import messages
from django.db.models import Sum, Count, F
from django.utils import timezone
from decimal import Decimal

from .models import AuditLog, SystemSettings
from .forms import SystemSettingsForm
from .utils import paginate
from apps.inventory.models import Product, ProductStock
from apps.sales.models import Sale, SaleItem
from apps.customers.models import Customer, Payment
from apps.warehouse.models import Warehouse


@has_permission('core.view_dashboard')
def dashboard(request):
    """Main dashboard view with key metrics."""
    today = timezone.localtime().date()
    month_start = today.replace(day=1)

    # Sales metrics. Cancelled sales keep their amounts on the row, so every
    # revenue/profit aggregate has to exclude them or the dashboard reports
    # money that was never earned.
    total_sales_today = Sale.objects.filter(
        sale_date=today, status=Sale.Status.COMPLETED
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    total_sales_month = Sale.objects.filter(
        sale_date__gte=month_start, status=Sale.Status.COMPLETED
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    # Cash Collection
    today_cash_collection = Payment.objects.filter(
        payment_date__date=today
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Profit calculation
    profit_month = SaleItem.objects.filter(
        sale__sale_date__gte=month_start,
        sale__status=Sale.Status.COMPLETED
    ).aggregate(
        profit=Sum((F('quantity') - F('returned_quantity')) * (F('unit_price') - F('cost_price')))
    )['profit'] or Decimal('0')
    
    # Inventory metrics
    total_products = Product.objects.filter(is_active=True).count()

    total_product_quantity = ProductStock.objects.filter(
        quantity__gt=0
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    # Get low stock threshold from settings
    from .models import SystemSettings
    db_settings = SystemSettings.get_settings()
    low_stock_threshold = db_settings.low_stock_threshold or 5
    
    low_stock_products = ProductStock.objects.filter(
        quantity__gt=0,
        quantity__lte=low_stock_threshold
    ).values('product').distinct().count()
    
    # Customer metrics
    total_customers = Customer.objects.count()
    total_dues = Customer.objects.aggregate(
        total=Sum('total_due')
    )['total'] or Decimal('0.00')
    
    # Warehouse metrics
    total_warehouses = Warehouse.objects.filter(is_active=True).count()
    
    # Recent sales. The template's Status column renders payment_status only, so
    # a cancelled sale would be badged "Unpaid" and look identical to a live one.
    recent_sales = Sale.objects.select_related('customer').exclude(
        status=Sale.Status.CANCELLED
    ).order_by('-sale_date')[:10]
    
    # Low stock alerts
    low_stock_items = ProductStock.objects.filter(
        quantity__gt=0,
        quantity__lte=low_stock_threshold
    ).select_related('product', 'warehouse').order_by('quantity')[:10]
    
    # Payment status counts for chart. Cancelling a sale leaves payment_status
    # untouched, so without this filter voided invoices are still tallied as
    # unpaid/partial.
    payment_status_counts = Sale.objects.exclude(
        status=Sale.Status.CANCELLED
    ).values('payment_status').annotate(count=Count('id'))
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
        'today_cash_collection': today_cash_collection,
        'profit_month': profit_month,
        'total_products': total_products,
        'total_product_quantity': total_product_quantity,
        'low_stock_products': low_stock_products,
        'total_customers': total_customers,
        'total_dues': total_dues,
        'total_warehouses': total_warehouses,
        'recent_sales': recent_sales,
        'low_stock_items': low_stock_items,
        'paid_count': paid_count,
        'partial_count': partial_count,
        'unpaid_count': unpaid_count,
    }
    return render(request, 'core/dashboard.html', context)


@has_permission('core.view_audit_logs')
def audit_logs(request):
    """View audit logs."""
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
    
    logs = paginate(request, logs, 25)

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
    from django.core.cache import cache
    
    ip = request.META.get('REMOTE_ADDR')
    cache_key = f'register_attempts_{ip}'
    attempts = cache.get(cache_key, 0)
    
    if attempts >= 10:
        messages.error(request, 'Too many registration attempts. Please try again later.')
        return render(request, 'core/register.html')
        
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        cache.set(cache_key, attempts + 1, 3600)
        
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
        elif password1 != password2:
            errors.append('Passwords do not match.')
        else:
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError
            try:
                validate_password(password1)
            except ValidationError as e:
                errors.extend(e.messages)
        
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
        return redirect('core:login')
    
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
        form = SystemSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            settings = form.save(commit=False)
            settings.updated_by = request.user
            settings.save()
    # Customer metrics
    total_customers = Customer.objects.count()
    total_dues = Customer.objects.aggregate(
        total=Sum('total_due')
    )['total'] or Decimal('0.00')
    
    # Warehouse metrics
    total_warehouses = Warehouse.objects.filter(is_active=True).count()
    
    # Recent sales. The template's Status column renders payment_status only, so
    # a cancelled sale would be badged "Unpaid" and look identical to a live one.
    recent_sales = Sale.objects.select_related('customer').exclude(
        status=Sale.Status.CANCELLED
    ).order_by('-sale_date')[:10]
    
    # Low stock alerts
    low_stock_items = ProductStock.objects.filter(
        quantity__gt=0,
        quantity__lte=low_stock_threshold
    ).select_related('product', 'warehouse').order_by('quantity')[:10]
    
    # Payment status counts for chart. Cancelling a sale leaves payment_status
    # untouched, so without this filter voided invoices are still tallied as
    # unpaid/partial.
    payment_status_counts = Sale.objects.exclude(
        status=Sale.Status.CANCELLED
    ).values('payment_status').annotate(count=Count('id'))
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
        'today_cash_collection': today_cash_collection,
        'profit_month': profit_month,
        'total_products': total_products,
        'total_product_quantity': total_product_quantity,
        'low_stock_products': low_stock_products,
        'total_customers': total_customers,
        'total_dues': total_dues,
        'total_warehouses': total_warehouses,
        'recent_sales': recent_sales,
        'low_stock_items': low_stock_items,
        'paid_count': paid_count,
        'partial_count': partial_count,
        'unpaid_count': unpaid_count,
    }
    return render(request, 'core/dashboard.html', context)


@has_permission('core.view_audit_logs')
def audit_logs(request):
    """View audit logs."""
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
    
    logs = paginate(request, logs, 25)

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
    from django.core.cache import cache
    
    ip = request.META.get('REMOTE_ADDR')
    cache_key = f'register_attempts_{ip}'
    attempts = cache.get(cache_key, 0)
    
    if attempts >= 10:
        messages.error(request, 'Too many registration attempts. Please try again later.')
        return render(request, 'core/register.html')
        
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        cache.set(cache_key, attempts + 1, 3600)
        
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
        elif password1 != password2:
            errors.append('Passwords do not match.')
        else:
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError
            try:
                temp_user = User(username=username, email=email, first_name=first_name, last_name=last_name)
                validate_password(password1, user=temp_user)
            except ValidationError as e:
                errors.extend(e.messages)
        
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
        return redirect('core:login')
    
    return render(request, 'core/register.html')


def is_superuser(user):
    """Check if user is superuser."""
    return user.is_superuser


from apps.core.decorators import has_permission

@login_required
@has_permission('core.change_systemsettings')
def system_settings(request):
    """View and update system settings."""
    settings = SystemSettings.get_settings()
    
    if request.method == 'POST':
        form = SystemSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            settings = form.save(commit=False)
            settings.updated_by = request.user
            settings.save()
            messages.success(request, 'System settings updated successfully.')
            return redirect('core:system_settings')
    else:
        form = SystemSettingsForm(instance=settings)
    
    context = {
        'form': form,
        'settings': settings,
    }
    return render(request, 'core/system_settings.html', context)

@login_required
def unauthorized(request):
    """View shown to logged-in users who lack the required role to view a page."""
    return render(request, 'core/unauthorized.html')

from apps.core.decorators import has_permission

@login_required
@has_permission('auth.view_user')
def staff_list(request):
    """List all staff members and handle new staff creation."""
    from .forms import StaffCreationForm
    
    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Successfully added staff member {form.cleaned_data["username"]}.')
            return redirect('core:staff_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StaffCreationForm()
        
    staff_members = User.objects.all().prefetch_related('groups').order_by('-is_superuser', 'username')
    roles = Group.objects.all()
    return render(request, 'core/staff_list.html', {
        'staff_members': staff_members,
        'roles': roles,
        'form': form
    })

@login_required
@has_permission('auth.change_user')
def update_staff_role(request, pk):
    """Update a staff member's role and status."""
    if request.method == 'POST':
        staff = get_object_or_404(User, pk=pk)
        
        # Don't allow modifying superusers through this interface
        if staff.is_superuser:
            messages.error(request, 'Cannot modify superuser roles through this interface.')
            return redirect('core:staff_list')
            
        # Update active status
        is_active = request.POST.get('is_active') == 'true'
        staff.is_active = is_active
        
        # Update role
        role_name = request.POST.get('role')
        staff.groups.clear()
        
        if role_name:
            try:
                group = Group.objects.get(name=role_name)
                staff.groups.add(group)
            except Group.DoesNotExist:
                pass
                
        staff.save()
        messages.success(request, f'Successfully updated settings for {staff.username}.')
    return redirect('core:staff_list')


@login_required
@has_permission('auth.change_user')
def update_staff_password(request, pk):
    """Update a staff member's password directly."""
    if request.method == 'POST':
        staff = get_object_or_404(User, pk=pk)
        
        # Don't allow modifying superusers through this interface unless it's yourself
        if staff.is_superuser and staff != request.user:
            messages.error(request, 'Cannot modify other superuser passwords through this interface.')
            return redirect('core:staff_list')
            
        new_password = request.POST.get('new_password')
        if new_password:
            staff.set_password(new_password)
            staff.save()
            messages.success(request, f'Successfully updated password for {staff.username}.')
        else:
            messages.error(request, 'Password cannot be empty.')
            
    return redirect('core:staff_list')


@login_required
@has_permission('auth.delete_user')
def delete_staff(request, pk):
    """Delete a staff member from the system."""
    if request.method == 'POST':
        staff = get_object_or_404(User, pk=pk)
        
        # Don't allow deleting superusers
        if staff.is_superuser:
            messages.error(request, 'Cannot delete a superuser. Demote them first if necessary.')
            return redirect('core:staff_list')
            
        username = staff.username
        staff.delete()
        messages.success(request, f'Staff member {username} deleted successfully.')
            
    return redirect('core:staff_list')


@login_required
def profile_update(request):
    from .forms import UserProfileForm
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile was successfully updated!')
            return redirect('core:dashboard')
    else:
        form = UserProfileForm(instance=request.user)
    
    return render(request, 'core/profile_update.html', {'form': form})


from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy

class CustomPasswordChangeView(PasswordChangeView):
    from .forms import CustomPasswordChangeForm
    form_class = CustomPasswordChangeForm
    template_name = 'core/password_change.html'
    success_url = reverse_lazy('core:dashboard')

    def form_valid(self, form):
        messages.success(self.request, 'Your password was successfully updated!')
        return super().form_valid(form)
