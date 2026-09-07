from django import forms
from .models import TelegramSetting


class TelegramSettingForm(forms.ModelForm):
    """Form for configuring the Telegram bot in the settings UI."""

    class Meta:
        model = TelegramSetting
        fields = ['bot_token', 'chat_id']
        widgets = {
            'bot_token': forms.PasswordInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 123456:ABC-DEF1234...',
                'autocomplete': 'off',
            }, render_value=True),
            'chat_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. -1001234567890',
            }),
        }
        labels = {
            'bot_token': 'Bot Token',
            'chat_id': 'Chat ID',
        }
        help_texts = {
            'bot_token': 'Get this from @BotFather on Telegram',
            'chat_id': 'The chat/group ID where notifications will be sent',
        }
