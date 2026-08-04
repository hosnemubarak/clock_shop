from django.db import models
from django.contrib.auth.models import User
from django.core.cache import cache


class AuditLog(models.Model):
    """Audit log for tracking all system changes."""
    class Action(models.TextChoices):
        CREATE = 'CREATE', 'Create'
        UPDATE = 'UPDATE', 'Update'
        DELETE = 'DELETE', 'Delete'
        TRANSFER = 'TRANSFER', 'Transfer'
        SALE = 'SALE', 'Sale'
        PAYMENT = 'PAYMENT', 'Payment'
        STOCK_IN = 'STOCK_IN', 'Stock In'
        STOCK_OUT = 'STOCK_OUT', 'Stock Out'
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    model_name = models.CharField(max_length=100)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object_repr = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
    
    def __str__(self):
        return f"{self.action} - {self.model_name} - {self.timestamp}"


class TimeStampedModel(models.Model):
    """Abstract base model with created and updated timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


class SystemSettings(models.Model):
    """
    Singleton model for system-wide settings.
    Values here override environment variables.
    """
    shop_name = models.CharField(
        max_length=200,
        blank=True,
        help_text='Shop name displayed across the system'
    )
    shop_address = models.TextField(
        blank=True,
        help_text='Shop address used on invoices and reports'
    )
    license_expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text='Server/license expiry date'
    )
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        help_text='Products with stock at or below this level are considered low stock'
    )
    alert_days_before_expiry = models.PositiveIntegerField(
        default=30,
        help_text='Number of days before expiry to start showing alerts'
    )
    currency_symbol = models.CharField(
        max_length=10,
        default='৳',
        help_text='Currency symbol for prices'
    )
    allow_walkin_customers = models.BooleanField(
        default=True,
        help_text='Allow sales to walk-in customers without an account'
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'
    
    def __str__(self):
        return 'System Settings'
    
    CACHE_KEY = 'core:system_settings'

    @classmethod
    def get_settings(cls):
        """Get or create the singleton settings instance."""
        # The global context processor calls this on every template render, which
        # was one query per request. The cache is per-process (LocMemCache), so a
        # save() in one gunicorn worker cannot invalidate its peers -- hence the
        # short timeout, which bounds how long a stale value can be served.
        cached = cache.get(cls.CACHE_KEY)
        if cached is not None:
            return cached
        settings, created = cls.objects.get_or_create(pk=1)
        cache.set(cls.CACHE_KEY, settings, 60)
        return settings

    def save(self, *args, **kwargs):
        self.pk = 1  # Ensure singleton
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)
