from django.contrib import admin
from .models import Category, Brand, Product, Batch, Purchase, PurchaseItem, StockOut, StockOutItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']
    list_per_page = 25


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']
    list_per_page = 25


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'category', 'brand', 'total_stock', 'default_selling_price', 'is_active', 'created_at']
    list_filter = ['category', 'brand', 'is_active', 'created_at']
    search_fields = ['sku', 'name', 'description']
    readonly_fields = ['total_stock', 'created_at', 'updated_at']
    ordering = ['name']
    list_per_page = 25
    fieldsets = (
        ('Basic Info', {
            'fields': ('sku', 'name', 'category', 'brand', 'description')
        }),
        ('Pricing', {
            'fields': ('default_selling_price',)
        }),
        ('Stock & Status', {
            'fields': ('total_stock', 'is_active')
        }),
        ('Media', {
            'fields': ('image',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ['batch_number', 'product', 'warehouse', 'buy_price', 'quantity', 'initial_quantity', 'purchase_date', 'supplier']
    list_filter = ['warehouse', 'purchase_date', 'product__category']
    search_fields = ['batch_number', 'product__name', 'product__sku', 'supplier']
    readonly_fields = ['batch_number', 'created_at', 'updated_at']
    ordering = ['-purchase_date', '-created_at']
    list_per_page = 25
    autocomplete_fields = ['product', 'warehouse']
    date_hierarchy = 'purchase_date'


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    readonly_fields = ['batch', 'product', 'quantity', 'unit_price']
    can_delete = False


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ['purchase_number', 'supplier', 'purchase_date', 'total_amount', 'created_by', 'created_at']
    list_filter = ['purchase_date', 'created_by']
    search_fields = ['purchase_number', 'supplier', 'notes']
    readonly_fields = ['purchase_number', 'created_at', 'updated_at']
    ordering = ['-purchase_date', '-created_at']
    list_per_page = 25
    inlines = [PurchaseItemInline]
    date_hierarchy = 'purchase_date'


class StockOutItemInline(admin.TabularInline):
    model = StockOutItem
    extra = 0
    readonly_fields = ['batch', 'quantity', 'cost_price']
    can_delete = False


@admin.register(StockOut)
class StockOutAdmin(admin.ModelAdmin):
    list_display = ['stockout_number', 'warehouse', 'reason', 'status', 'total_value', 'stockout_date', 'created_by']
    list_filter = ['status', 'reason', 'warehouse', 'stockout_date']
    search_fields = ['stockout_number', 'notes']
    readonly_fields = ['stockout_number', 'total_value', 'completed_date', 'created_at', 'updated_at']
    ordering = ['-stockout_date', '-created_at']
    list_per_page = 25
    inlines = [StockOutItemInline]
    date_hierarchy = 'stockout_date'
    
    def has_change_permission(self, request, obj=None):
        if obj and obj.status in ['completed', 'cancelled']:
            return False
        return super().has_change_permission(request, obj)
