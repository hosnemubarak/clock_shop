from django.db import models
from django.core.cache import cache


class TelegramSetting(models.Model):
    """Singleton model for Telegram bot configuration."""
    bot_token = models.CharField(
        max_length=255,
        blank=True,
        help_text='Telegram Bot API token (from @BotFather)'
    )
    chat_id = models.CharField(
        max_length=100,
        blank=True,
        help_text='Telegram chat/group ID to send notifications to'
    )
    apprise_url = models.CharField(
        max_length=500,
        blank=True,
        editable=False,
        help_text='Auto-built Apprise URL from bot_token and chat_id'
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('inactive', 'Inactive'),
        ],
        default='inactive',
    )
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Telegram Setting'
        verbose_name_plural = 'Telegram Settings'

    def __str__(self):
        status_display = self.get_status_display()
        return f'Telegram Config ({status_display})'

    CACHE_KEY = 'notifications:telegram_settings'

    @classmethod
    def get_settings(cls):
        """Get or create the singleton settings instance (cached)."""
        cached = cache.get(cls.CACHE_KEY)
        if cached is not None:
            return cached
        settings, _ = cls.objects.get_or_create(pk=1)
        if (settings.bot_token and settings.chat_id) and not settings.apprise_url:
            settings.save()
        cache.set(cls.CACHE_KEY, settings, 60)
        return settings

    def build_apprise_url(self):
        """Build the Apprise Telegram URL from bot_token and chat_id."""
        if self.bot_token and self.chat_id:
            return f'tgram://{self.bot_token.strip()}/{str(self.chat_id).strip()}/'
        return ''

    def save(self, *args, **kwargs):
        self.pk = 1  # Ensure singleton
        self.apprise_url = self.build_apprise_url()
        if not self.apprise_url:
            self.status = 'inactive'
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)


class NotificationLog(models.Model):
    """Log of sent notifications for deduplication and auditing."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENDING = 'sending', 'Sending'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'

    event_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text='e.g. sale_created, payment_received'
    )
    event_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Unique identifier for the event (e.g. sale PK)'
    )
    message = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_message = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    send_started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['event_type', 'event_id'],
                name='unique_notification_event',
            ),
        ]

    def __str__(self):
        return f'{self.event_type}:{self.event_id} — {self.status}'
