from django.contrib import admin
from django.utils.html import format_html
from .models import Customer, Payment, CustomerNote


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ['amount', 'payment_method', 'payment_date', 'sale', 'reference', 'received_by']
    can_delete = False
    max_num = 10
    
    def has_add_permission(self, request, obj=None):
        return False


class CustomerNoteInline(admin.TabularInline):
    model = CustomerNote
    extra = 0
    readonly_fields = ['note', 'created_at', 'created_by']


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'total_purchases', 'total_paid', 
                    'balance_display', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'phone', 'email', 'address']
    readonly_fields = ['total_purchases', 'total_paid', 'total_due', 'created_at', 'updated_at']
    ordering = ['name']
    list_per_page = 25
    inlines = [PaymentInline, CustomerNoteInline]
    
    fieldsets = (
        ('Contact Info', {
            'fields': ('name', 'phone', 'email', 'address')
        }),
        ('Financial', {
            'fields': ('total_purchases', 'total_paid', 'total_due', 'credit_limit')
        }),
        ('Status & Notes', {
            'fields': ('is_active', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def balance_display(self, obj):
        if obj.total_due > 0:
            return format_html('<span style="color: red; font-weight: bold;">৳{}</span>', obj.total_due)
        return format_html('<span style="color: green;">৳{}</span>', obj.total_due)
    balance_display.short_description = 'Balance Due'


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'amount', 'payment_method', 'payment_date', 
                    'sale', 'reference', 'received_by']
    list_filter = ['payment_method', 'payment_date', 'received_by']
    search_fields = ['customer__name', 'customer__phone', 'reference', 'sale__invoice_number']
    readonly_fields = ['payment_date', 'created_at', 'updated_at']
    ordering = ['-payment_date']
    list_per_page = 25
    date_hierarchy = 'payment_date'
    autocomplete_fields = ['customer', 'sale']


@admin.register(CustomerNote)
class CustomerNoteAdmin(admin.ModelAdmin):
    list_display = ['customer', 'note_preview', 'created_at', 'created_by']
    list_filter = ['created_at', 'created_by']
    search_fields = ['customer__name', 'note']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 25
    
    def note_preview(self, obj):
        return obj.note[:50] + '...' if len(obj.note) > 50 else obj.note
    note_preview.short_description = 'Note'
