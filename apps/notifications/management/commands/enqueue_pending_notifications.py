from django.core.management.base import BaseCommand

from apps.notifications.models import NotificationLog
from apps.notifications.services import enqueue_notification


class Command(BaseCommand):
    help = 'Enqueue pending Telegram notifications that were not dispatched.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        pending = NotificationLog.objects.filter(
            status=NotificationLog.Status.PENDING,
        ).order_by('created_at')[:options['limit']]
        count = 0
        for log_entry in pending:
            if enqueue_notification(log_entry):
                count += 1
        self.stdout.write(self.style.SUCCESS(f'Enqueued {count} pending notification(s).'))
