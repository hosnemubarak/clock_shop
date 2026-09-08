import logging

import apprise
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def enqueue_notification(log_entry):
    """Enqueue one durable notification using its stable RQ job ID."""
    try:
        import django_rq
        queue = django_rq.get_queue('default')
        from .tasks import send_notification_task
        job_id = f'notification-{log_entry.pk}'
        if queue.fetch_job(job_id) is None:
            queue.enqueue(send_notification_task, log_entry.pk, job_id=job_id)
        return True
    except Exception:
        logger.warning(
            'Redis/RQ enqueue failed for notification log %s', log_entry.pk,
            exc_info=True,
        )
        try:
            log_entry.error_message = 'Failed to enqueue notification in RQ'
            log_entry.save(update_fields=['error_message'])
        except Exception:
            logger.exception('Unable to record notification enqueue failure')
        return False


def _get_apprise_url():
    """Return the configured Apprise Telegram URL, or empty string."""
    from .models import TelegramSetting
    settings = TelegramSetting.get_settings()
    return settings.apprise_url


def send_telegram(message, apprise_url=None):
    """Send a plain-text message via Apprise to Telegram.

    Returns True on success, raises on failure.
    """
    url = apprise_url or _get_apprise_url()
    if not url:
        raise ValueError('Telegram is not configured (missing bot_token or chat_id)')

    # Apprise Telegram HTML mode collapses consecutive newlines (\n\n -> \n).
    # Inserting a zero-width space (\u200b) on blank lines preserves the spacing in Telegram.
    if message:
        import re
        message = re.sub(r'\n\s*\n', '\n\u200b\n', message)

    ap = apprise.Apprise()
    ap.add(url)
    result = ap.notify(body=message, notify_type=apprise.NotifyType.INFO)

    if not result:
        raise RuntimeError(
            'Failed to deliver Telegram notification. '
            'Please verify that your Bot Token is valid, the Chat ID is correct, '
            'and you have started a chat with your bot (send /start to the bot in Telegram).'
        )

    return True


def send_test_notification(bot_token=None, chat_id=None):
    """Send a test notification and update TelegramSetting status.

    Can test with credentials passed directly from the form or with saved DB settings.
    On success, updates and saves the working credentials and sets status to 'active'.
    Returns (success: bool, error_message: str).
    """
    from .models import TelegramSetting

    settings = TelegramSetting.get_settings()
    token = (str(bot_token).strip() if bot_token else '') or settings.bot_token
    cid = (str(chat_id).strip() if chat_id else '') or settings.chat_id

    if not token or not cid:
        return False, 'Telegram is not configured. Please enter bot token and chat ID.'

    test_url = f'tgram://{token}/{cid}/'

    try:
        send_telegram('✅ Test notification — Telegram is configured correctly!', apprise_url=test_url)
        settings.bot_token = token
        settings.chat_id = cid
        settings.status = 'active'
        settings.last_tested_at = timezone.now()
        settings.save()
        return True, ''
    except Exception as e:
        if settings.bot_token == token and settings.chat_id == cid:
            settings.status = 'inactive'
            settings.last_tested_at = timezone.now()
            settings.save()
        logger.exception('Telegram test notification failed')
        return False, str(e)


def notify(event_type, event_id, message):
    """Create a NotificationLog entry and enqueue the background send task.

    This function is designed to **never raise an exception**.  It is called
    from Django signal handlers during sale/payment saves, so any unhandled
    error here would roll back the business transaction.  Every code path is
    wrapped in try/except and failures are logged instead of propagated.

    Deduplication is enforced by the database constraint on (event_type,
    event_id). Dispatch is RQ-only; notification delivery must never run in a
    request thread or an untracked daemon thread.
    """
    try:
        from .models import TelegramSetting, NotificationLog

        log_entry, created = NotificationLog.objects.get_or_create(
            event_type=event_type,
            event_id=str(event_id),
            defaults={
                'message': message,
            },
        )
        if not created:
            logger.debug('Duplicate notification skipped: %s:%s', event_type, event_id)
            return None

        def _enqueue():
            enqueue_notification(log_entry)

        if transaction.get_autocommit():
            _enqueue()
        else:
            transaction.on_commit(_enqueue)

        return log_entry

    except Exception:
        # Ultimate safety net — absolutely nothing from the notification
        # subsystem is allowed to propagate to the caller.
        logger.exception(
            'Unexpected error in notify(%s, %s) — notification dropped', event_type, event_id,
        )
        return None
