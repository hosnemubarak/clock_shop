from django.contrib import admin
from django.utils.html import format_html
from .models import Sale, SaleItem, SaleReturn, SaleReturnItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ['product', 'batch', 'quantity', 'unit_price', 'cost_price', 'discount', 'is_custom', 'custom_description']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'customer', 'sale_date', 'total_amount', 
                    'paid_amount', 'payment_status_badge', 'status_badge', 'created_by']
    list_filter = ['status', 'payment_status', 'sale_date', 'created_by']
    search_fields = ['invoice_number', 'customer__name', 'customer__phone', 'notes']
    readonly_fields = ['invoice_number', 'subtotal', 'total_cost', 'created_at', 'updated_at']
    ordering = ['-sale_date', '-created_at']
    list_per_page = 25
    inlines = [SaleItemInline]
    date_hierarchy = 'sale_date'
    autocomplete_fields = ['customer']
    
    fieldsets = (
        ('Invoice Info', {
            'fields': ('invoice_number', 'customer', 'sale_date', 'status')
        }),
        ('Amounts', {
            'fields': ('subtotal', 'discount_amount', 'tax_amount', 'total_amount', 'total_cost')
        }),
        ('Payment', {
            'fields': ('paid_amount', 'payment_status')
        }),
        ('Additional', {
            'fields': ('notes', 'created_by'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def payment_status_badge(self, obj):
        colors = {'paid': 'green', 'partial': 'orange', 'unpaid': 'red'}
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.payment_status, 'gray'),
            obj.get_payment_status_display()
        )
    payment_status_badge.short_description = 'Payment'
    
    def status_badge(self, obj):
        colors = {'completed': 'green', 'pending': 'orange', 'cancelled': 'red'}
        return format_html(
            '<span style="color: {};">{}</span>',
            colors.get(obj.status, 'gray'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


class SaleReturnItemInline(admin.TabularInline):
    model = SaleReturnItem
    extra = 0
    readonly_fields = ['sale_item', 'quantity']


@admin.register(SaleReturn)
class SaleReturnAdmin(admin.ModelAdmin):
    list_display = ['return_number', 'sale', 'return_date', 'refund_amount', 'reason', 'created_by']
    list_filter = ['return_date', 'created_by']
    search_fields = ['return_number', 'sale__invoice_number', 'reason']
    readonly_fields = ['return_number', 'created_at', 'updated_at']
    ordering = ['-return_date', '-created_at']
    list_per_page = 25
    inlines = [SaleReturnItemInline]
    date_hierarchy = 'return_date'
