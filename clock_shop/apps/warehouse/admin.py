from django.contrib import admin
from django.utils.html import format_html
from .models import Warehouse, StockTransfer, StockTransferItem


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'phone', 'is_shop', 'is_active', 'stock_summary', 'created_at']
    list_filter = ['is_active', 'is_shop', 'created_at']
    search_fields = ['name', 'code', 'address', 'phone']
    ordering = ['name']
    list_per_page = 25
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'code', 'phone', 'address')
        }),
        ('Settings', {
            'fields': ('is_shop', 'is_active')
        }),
    )
    
    def stock_summary(self, obj):
        items = obj.get_total_items()
        value = obj.get_total_stock_value()
        return format_html('{} items (৳{})', items, value)
    stock_summary.short_description = 'Stock'


class StockTransferItemInline(admin.TabularInline):
    model = StockTransferItem
    extra = 0
    readonly_fields = ['source_batch', 'destination_batch', 'quantity']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ['transfer_number', 'source_warehouse', 'destination_warehouse', 
                    'status_badge', 'transfer_date', 'completed_date', 'created_by']
    list_filter = ['status', 'transfer_date', 'source_warehouse', 'destination_warehouse']
    search_fields = ['transfer_number', 'notes']
    readonly_fields = ['transfer_number', 'completed_date', 'created_at', 'updated_at']
    ordering = ['-transfer_date', '-created_at']
    list_per_page = 25
    inlines = [StockTransferItemInline]
    date_hierarchy = 'transfer_date'
    
    fieldsets = (
        ('Transfer Info', {
            'fields': ('transfer_number', 'source_warehouse', 'destination_warehouse', 'transfer_date')
        }),
        ('Status', {
            'fields': ('status', 'completed_date')
        }),
        ('Additional', {
            'fields': ('notes', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        colors = {'completed': 'green', 'pending': 'orange', 'cancelled': 'red'}
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'gray'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def has_change_permission(self, request, obj=None):
        if obj and obj.status in ['completed', 'cancelled']:
            return False
        return super().has_change_permission(request, obj)
