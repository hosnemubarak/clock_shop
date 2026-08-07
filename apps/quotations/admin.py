from django.contrib import admin
from .models import Quotation, QuotationItem


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 0
    readonly_fields = ('total_price',)


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ('quotation_number', 'title', 'client_name', 'quotation_date', 'status', 'total_amount')
    list_filter = ('status', 'quotation_date')
    search_fields = ('quotation_number', 'title', 'client_name')
    date_hierarchy = 'quotation_date'
    inlines = [QuotationItemInline]
