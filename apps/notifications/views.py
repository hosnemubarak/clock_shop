import json
import logging

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .services import send_test_notification

logger = logging.getLogger(__name__)


def can_test_telegram(user):
    return user.is_authenticated and (user.is_superuser or user.has_perm('core.change_systemsettings'))


@login_required
@user_passes_test(can_test_telegram)
@require_POST
def test_telegram(request):
    """AJAX endpoint to test the Telegram configuration."""
    bot_token = None
    chat_id = None

    if request.body:
        try:
            data = json.loads(request.body)
            bot_token = data.get('bot_token')
            chat_id = data.get('chat_id')
        except (json.JSONDecodeError, AttributeError):
            pass

    success, error = send_test_notification(bot_token=bot_token, chat_id=chat_id)

    if success:
        return JsonResponse({
            'success': True,
            'message': 'Test notification sent successfully! Check your Telegram.',
        })
    else:
        return JsonResponse({
            'success': False,
            'message': f'Test failed: {error}',
        }, status=400)
