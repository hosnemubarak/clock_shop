from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncMonth
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
    )['total'] or Decimal('0')
    
    # Recent sales
    recent_sales = Sale.objects.select_related('customer').order_by('-sale_date')[:10]
    
    # Low stock alerts
    low_stock_batches = Batch.objects.filter(
        quantity__gt=0,
        quantity__lte=10
    ).select_related('product', 'warehouse').order_by('quantity')[:10]
    
    # Monthly sales chart data
    six_months_ago = today - timedelta(days=180)
    monthly_sales = Sale.objects.filter(
        sale_date__date__gte=six_months_ago
    ).annotate(
        month=TruncMonth('sale_date')
    ).values('month').annotate(
        total=Sum('total_amount')
    ).order_by('month')
    
    context = {
        'total_sales_today': total_sales_today,
        'total_sales_month': total_sales_month,
        'profit_month': profit_month,
        'total_products': total_products,
        'low_stock_products': low_stock_products,
        'total_customers': total_customers,
        'total_dues': total_dues,
        'recent_sales': recent_sales,
        'low_stock_batches': low_stock_batches,
        'monthly_sales': list(monthly_sales),
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def audit_logs(request):
    """View audit logs."""
    logs = AuditLog.objects.select_related('user').all()[:100]
    return render(request, 'core/audit_logs.html', {'logs': logs})
