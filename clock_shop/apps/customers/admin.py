from django.contrib import admin
from .models import Customer, Payment, CustomerNote


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'total_purchases', 'total_paid', 
                    'total_due', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'phone', 'email']
    readonly_fields = ['total_purchases', 'total_paid', 'total_due']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['customer', 'amount', 'payment_method', 'payment_date', 
                    'sale', 'received_by']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['customer__name', 'reference']
    readonly_fields = ['payment_date']


@admin.register(CustomerNote)
class CustomerNoteAdmin(admin.ModelAdmin):
    list_display = ['customer', 'created_at', 'created_by']
    list_filter = ['created_at']
    search_fields = ['customer__name', 'note']
