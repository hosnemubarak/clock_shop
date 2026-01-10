from django.contrib import admin
from .models import Category, Brand, Product, Batch, Purchase, PurchaseItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'category', 'brand', 'total_stock', 'default_selling_price', 'is_active']
    list_filter = ['category', 'brand', 'is_active']
    search_fields = ['sku', 'name']
    readonly_fields = ['total_stock']


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ['batch_number', 'product', 'warehouse', 'buy_price', 'quantity', 'initial_quantity', 'purchase_date']
    list_filter = ['warehouse', 'purchase_date']
    search_fields = ['batch_number', 'product__name']
    readonly_fields = ['batch_number']


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    readonly_fields = ['batch', 'product', 'quantity', 'unit_price']


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ['purchase_number', 'supplier', 'purchase_date', 'total_amount', 'created_by']
    list_filter = ['purchase_date']
    search_fields = ['purchase_number', 'supplier']
    readonly_fields = ['purchase_number']
    inlines = [PurchaseItemInline]
