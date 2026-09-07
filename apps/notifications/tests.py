import json
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.notifications.models import TelegramSetting
from apps.notifications.services import send_test_notification
from apps.notifications.signals import format_sale_message, format_payment_message
from apps.sales.models import Sale
from apps.customers.models import Customer, Payment


class TelegramNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin_test',
            email='admin@example.com',
            password='password123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_send_test_notification_without_config_fails(self):
        success, error = send_test_notification()
        self.assertFalse(success)
        self.assertIn('Telegram is not configured', error)

    @patch('apps.notifications.services.send_telegram')
    def test_send_test_notification_with_params_succeeds(self, mock_send):
        mock_send.return_value = True

        success, error = send_test_notification(
            bot_token='123456:TEST_TOKEN',
            chat_id='-100123456789'
        )
        self.assertTrue(success)
        self.assertEqual(error, '')

        settings = TelegramSetting.get_settings()
        self.assertEqual(settings.bot_token, '123456:TEST_TOKEN')
        self.assertEqual(settings.chat_id, '-100123456789')
        self.assertEqual(settings.status, 'active')
        self.assertIsNotNone(settings.last_tested_at)
        self.assertEqual(settings.apprise_url, 'tgram://123456:TEST_TOKEN/-100123456789/')

    @patch('apps.notifications.services.send_telegram')
    def test_ajax_test_telegram_endpoint_with_payload(self, mock_send):
        mock_send.return_value = True

        url = reverse('notifications:test_telegram')
        response = self.client.post(
            url,
            data=json.dumps({
                'bot_token': '987654:ANOTHER_TOKEN',
                'chat_id': '12345678'
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('Test notification sent successfully', data['message'])

        settings = TelegramSetting.get_settings()
        self.assertEqual(settings.bot_token, '987654:ANOTHER_TOKEN')
        self.assertEqual(settings.chat_id, '12345678')
        self.assertEqual(settings.status, 'active')

    def test_ajax_test_telegram_endpoint_without_credentials(self):
        url = reverse('notifications:test_telegram')
        response = self.client.post(
            url,
            data=json.dumps({'bot_token': '', 'chat_id': ''}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Telegram is not configured', data['message'])

    def test_format_sale_message_meaningful_content(self):
        customer = Customer.objects.create(
            name='Tanvir Hasan',
            phone='01711223344',
            total_due=Decimal('500.00')
        )
        sale = Sale.objects.create(
            customer=customer,
            sale_date=timezone.localdate(),
            total_amount=Decimal('1500.00'),
            paid_amount=Decimal('1000.00'),
            payment_status='partial',
            created_by=self.user,
            status=Sale.Status.COMPLETED
        )
        msg = format_sale_message(sale)

        self.assertIn('New Sale Created', msg)
        self.assertIn(sale.invoice_number, msg)
        self.assertIn('Tanvir Hasan', msg)
        self.assertIn('01711223344', msg)
        self.assertIn('Partially Paid', msg)
        self.assertIn('1,500.00', msg)
        self.assertIn('1,000.00', msg)
        self.assertIn('500.00', msg)
        self.assertIn('Customer Total Due:', msg)
        self.assertIn('admin_test', msg)

    def test_format_payment_message_meaningful_content(self):
        customer = Customer.objects.create(
            name='Tanvir Hasan',
            phone='01711223344',
            total_due=Decimal('0.00')
        )
        sale = Sale.objects.create(
            customer=customer,
            sale_date=timezone.localdate(),
            total_amount=Decimal('1000.00'),
            paid_amount=Decimal('500.00'),
            payment_status='partial',
            status=Sale.Status.COMPLETED
        )
        payment = Payment.objects.create(
            customer=customer,
            sale=sale,
            amount=Decimal('500.00'),
            payment_method='cash',
            received_by=self.user
        )
        msg = format_payment_message(payment)

        self.assertIn('Payment Received', msg)
        self.assertIn('500.00', msg)
        self.assertIn('Cash', msg)
        self.assertIn('Tanvir Hasan', msg)
        self.assertIn(sale.invoice_number, msg)
        self.assertIn('Partially Paid', msg)
        self.assertIn('admin_test', msg)
