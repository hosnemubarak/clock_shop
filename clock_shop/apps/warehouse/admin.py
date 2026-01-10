from django.contrib import admin
from .models import Warehouse, StockTransfer, StockTransferItem


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'is_shop', 'created_at']
    list_filter = ['is_active', 'is_shop']
    search_fields = ['name', 'code']


class StockTransferItemInline(admin.TabularInline):
    model = StockTransferItem
    extra = 0
    readonly_fields = ['source_batch', 'destination_batch', 'quantity']


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ['transfer_number', 'source_warehouse', 'destination_warehouse', 
                    'status', 'transfer_date', 'created_by']
    list_filter = ['status', 'transfer_date']
    search_fields = ['transfer_number']
    readonly_fields = ['transfer_number', 'completed_date']
    inlines = [StockTransferItemInline]
