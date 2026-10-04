from django.contrib import admin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from import_export.admin import ImportExportModelAdmin
from .models import Category, Brand, Product, ProductStock, Purchase, PurchaseItem, StockOut, StockOutItem


class CategoryResource(resources.ModelResource):
    id = fields.Field(attribute='id', column_name='id', readonly=True)
    created_at = fields.Field(attribute='created_at', column_name='created_at', readonly=True)
    updated_at = fields.Field(attribute='updated_at', column_name='updated_at', readonly=True)

    class Meta:
        model = Category
        fields = ('id', 'name', 'description', 'is_active', 'created_at', 'updated_at')
        export_order = ('id', 'name', 'description', 'is_active', 'created_at', 'updated_at')
        import_id_fields = ('name',)
        skip_unchanged = True
        report_skipped = True


class BrandResource(resources.ModelResource):
    id = fields.Field(attribute='id', column_name='id', readonly=True)
    created_at = fields.Field(attribute='created_at', column_name='created_at', readonly=True)
    updated_at = fields.Field(attribute='updated_at', column_name='updated_at', readonly=True)

    class Meta:
        model = Brand
        fields = ('id', 'name', 'description', 'is_active', 'created_at', 'updated_at')
        export_order = ('id', 'name', 'description', 'is_active', 'created_at', 'updated_at')
        import_id_fields = ('name',)
        skip_unchanged = True
        report_skipped = True


class ProductResource(resources.ModelResource):
    id = fields.Field(attribute='id', column_name='id', readonly=True)
    created_at = fields.Field(attribute='created_at', column_name='created_at', readonly=True)
    updated_at = fields.Field(attribute='updated_at', column_name='updated_at', readonly=True)
    total_stock = fields.Field(attribute='total_stock', column_name='total_stock', readonly=True)
    average_cost = fields.Field(attribute='average_cost', column_name='average_cost', readonly=True)

    category = fields.Field(
        column_name='category',
        attribute='category',
        widget=ForeignKeyWidget(Category, field='name')
    )
    brand = fields.Field(
        column_name='brand',
        attribute='brand',
        widget=ForeignKeyWidget(Brand, field='name')
    )

    class Meta:
        model = Product
        fields = ('id', 'sku', 'brand', 'category', 'description', 'default_selling_price', 'total_stock', 'average_cost', 'is_active', 'created_at', 'updated_at')
        export_order = ('id', 'sku', 'brand', 'category', 'description', 'default_selling_price', 'total_stock', 'average_cost', 'is_active', 'created_at', 'updated_at')
        import_id_fields = ('sku',)
        skip_unchanged = True
        report_skipped = True


@admin.register(Category)
class CategoryAdmin(ImportExportModelAdmin):
    resource_classes = [CategoryResource]
    list_display = ['name', 'description', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']
    list_per_page = 25


@admin.register(Brand)
class BrandAdmin(ImportExportModelAdmin):
    resource_classes = [BrandResource]
    list_display = ['name', 'description', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']
    list_per_page = 25


@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    resource_classes = [ProductResource]
    list_display = ['sku', 'brand', 'category', 'total_stock', 'default_selling_price', 'is_active', 'created_at']
    list_filter = ['category', 'brand', 'is_active', 'created_at']
    search_fields = ['sku', 'brand__name', 'description']
    readonly_fields = ['total_stock', 'created_at', 'updated_at']
    ordering = ['sku']
    list_per_page = 25
    fieldsets = (
        ('Basic Info', {
            'fields': ('sku', 'brand', 'category', 'description')
        }),
        ('Pricing', {
            'fields': ('default_selling_price',)
        }),
        ('Stock & Status', {
            'fields': ('total_stock', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ProductStock)
class ProductStockAdmin(admin.ModelAdmin):
    list_display = ['product', 'warehouse', 'quantity', 'created_at']
    list_filter = ['warehouse']
    search_fields = ['product__sku', 'product__brand__name']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 25
    autocomplete_fields = ['product', 'warehouse']


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    readonly_fields = ['product', 'warehouse', 'quantity', 'unit_price']
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
    readonly_fields = ['product', 'quantity', 'cost_price']
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
