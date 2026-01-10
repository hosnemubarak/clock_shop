from django.contrib import admin
from .models import Sale, SaleItem, SaleReturn, SaleReturnItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ['product', 'batch', 'quantity', 'unit_price', 'cost_price', 'discount']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'customer', 'sale_date', 'total_amount', 
                    'paid_amount', 'payment_status', 'status']
    list_filter = ['status', 'payment_status', 'sale_date']
    search_fields = ['invoice_number', 'customer__name']
    readonly_fields = ['invoice_number', 'subtotal', 'total_cost']
    inlines = [SaleItemInline]


class SaleReturnItemInline(admin.TabularInline):
    model = SaleReturnItem
    extra = 0


@admin.register(SaleReturn)
class SaleReturnAdmin(admin.ModelAdmin):
    list_display = ['return_number', 'sale', 'return_date', 'refund_amount']
    list_filter = ['return_date']
    search_fields = ['return_number', 'sale__invoice_number']
    readonly_fields = ['return_number']
    inlines = [SaleReturnItemInline]
