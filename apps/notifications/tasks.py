import logging
import time

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_RETRIES = getattr(settings, 'NOTIFICATION_MAX_RETRIES', 3)
RETRY_DELAYS = [10, 30, 60]  # seconds: exponential-ish backoff


def send_notification_task(notification_log_id):
    """Background task: send a notification and update the log entry.

    Retries up to MAX_RETRIES times with exponential backoff on failure.
    """
    from .models import NotificationLog, TelegramSetting
    from .services import send_telegram

    try:
        log_entry = NotificationLog.objects.get(pk=notification_log_id)
    except NotificationLog.DoesNotExist:
        logger.error('NotificationLog %s not found', notification_log_id)
        return

    # Skip if already sent
    if log_entry.status == NotificationLog.Status.SENT:
        return

    telegram_settings = TelegramSetting.get_settings()
    apprise_url = telegram_settings.apprise_url
    if not apprise_url:
        log_entry.status = NotificationLog.Status.FAILED
        log_entry.error_message = 'Telegram not configured'
        log_entry.save(update_fields=['status', 'error_message'])
        return

    last_error = ''
    for attempt in range(1, MAX_RETRIES + 1):
        log_entry.attempts = attempt
        try:
            send_telegram(log_entry.message, apprise_url=apprise_url)

            # Success
            log_entry.status = NotificationLog.Status.SENT
            log_entry.error_message = ''
            log_entry.sent_at = timezone.now()
            log_entry.save(update_fields=['status', 'error_message', 'attempts', 'sent_at'])

            # Update last_notified_at on settings
            telegram_settings.last_notified_at = timezone.now()
            telegram_settings.save(update_fields=['last_notified_at', 'updated_at'])

            logger.info('Notification sent: %s:%s (attempt %d)', log_entry.event_type, log_entry.event_id, attempt)
            return

        except Exception as e:
            last_error = str(e)
            logger.warning(
                'Notification attempt %d/%d failed for %s:%s — %s',
                attempt, MAX_RETRIES, log_entry.event_type, log_entry.event_id, last_error
            )
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]
                time.sleep(delay)

    # All retries exhausted
    log_entry.status = NotificationLog.Status.FAILED
    log_entry.error_message = last_error
    log_entry.save(update_fields=['status', 'error_message', 'attempts'])
    logger.error('Notification failed after %d attempts: %s:%s', MAX_RETRIES, log_entry.event_type, log_entry.event_id)
