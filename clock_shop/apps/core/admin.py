from django.contrib import admin
from django.utils.html import format_html
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'action_badge', 'model_name', 'object_repr', 'ip_address']
    list_filter = ['action', 'model_name', 'timestamp', 'user']
    search_fields = ['object_repr', 'user__username', 'model_name', 'ip_address']
    readonly_fields = ['timestamp', 'user', 'action', 'model_name', 'object_id', 
                       'object_repr', 'changes', 'ip_address']
    ordering = ['-timestamp']
    list_per_page = 50
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Event Info', {
            'fields': ('timestamp', 'user', 'action', 'ip_address')
        }),
        ('Object Info', {
            'fields': ('model_name', 'object_id', 'object_repr')
        }),
        ('Changes', {
            'fields': ('changes',),
            'classes': ('collapse',)
        }),
    )
    
    def action_badge(self, obj):
        colors = {
            'CREATE': '#28a745',
            'UPDATE': '#17a2b8', 
            'DELETE': '#dc3545',
            'SALE': '#6f42c1',
            'PAYMENT': '#20c997',
            'STOCK_IN': '#007bff',
            'STOCK_OUT': '#fd7e14',
            'TRANSFER': '#6610f2',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.action, '#6c757d'),
            obj.get_action_display()
        )
    action_badge.short_description = 'Action'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
