from django.contrib import admin
from .models import TelegramSetting, NotificationLog


@admin.register(TelegramSetting)
class TelegramSettingAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'status', 'last_tested_at', 'last_notified_at', 'updated_at']
    readonly_fields = ['apprise_url', 'status', 'last_tested_at', 'last_notified_at', 'created_at', 'updated_at']

    def has_add_permission(self, request):
        # Singleton: only one instance allowed
        return not TelegramSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'event_id', 'status', 'attempts', 'created_at', 'send_started_at', 'sent_at']
    list_filter = ['status', 'event_type']
    search_fields = ['event_type', 'event_id', 'message']
    readonly_fields = ['event_type', 'event_id', 'message', 'status', 'error_message', 'attempts', 'created_at', 'send_started_at', 'sent_at']
    ordering = ['-created_at']

    def has_add_permission(self, request):
        return False
