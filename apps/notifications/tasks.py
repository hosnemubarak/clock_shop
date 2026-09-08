import logging

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

def send_notification_task(notification_log_id):
    """Background task: send a notification and update the log entry.

    Claims the row before the external call and sends at most once. This is
    intentionally at-most-once: an ambiguous provider timeout must not cause
    an automatic duplicate Telegram message.
    """
    from .models import NotificationLog, TelegramSetting
    from .services import send_telegram

    try:
        log_entry = NotificationLog.objects.get(pk=notification_log_id)
    except NotificationLog.DoesNotExist:
        logger.error('NotificationLog %s not found', notification_log_id)
        return

    if log_entry.status in (NotificationLog.Status.SENT, NotificationLog.Status.FAILED,
                            NotificationLog.Status.SENDING):
        return

    telegram_settings = TelegramSetting.get_settings()
    apprise_url = telegram_settings.apprise_url
    if not apprise_url:
        log_entry.status = NotificationLog.Status.FAILED
        log_entry.error_message = 'Telegram not configured'
        log_entry.attempts = 1
        log_entry.save(update_fields=['status', 'error_message', 'attempts'])
        return

    # This conditional update is the cross-process idempotency claim.
    claimed = NotificationLog.objects.filter(
        pk=notification_log_id,
        status=NotificationLog.Status.PENDING,
    ).update(
        status=NotificationLog.Status.SENDING,
        attempts=F('attempts') + 1,
        send_started_at=timezone.now(),
        error_message='',
    )
    if not claimed:
        return

    log_entry.refresh_from_db()
    try:
        send_telegram(log_entry.message, apprise_url=apprise_url)
    except Exception as exc:
        log_entry.status = NotificationLog.Status.FAILED
        log_entry.error_message = str(exc)
        log_entry.save(update_fields=['status', 'error_message'])
        logger.error('Notification failed after one attempt: %s:%s', log_entry.event_type, log_entry.event_id)
        return

    log_entry.status = NotificationLog.Status.SENT
    log_entry.error_message = ''
    log_entry.sent_at = timezone.now()
    log_entry.save(update_fields=['status', 'error_message', 'sent_at'])
    try:
        telegram_settings.last_notified_at = timezone.now()
        telegram_settings.save(update_fields=['last_notified_at', 'updated_at'])
    except Exception:
        logger.exception('Unable to update Telegram last_notified_at')
    logger.info('Notification sent: %s:%s', log_entry.event_type, log_entry.event_id)
