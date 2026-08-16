"""Tests for customer financial views and APIs."""

from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLog
from apps.customers.models import Customer, Payment
from apps.customers.views import _customer_loyalty
from apps.sales.models import Sale, SaleReturn


@override_settings(SECURE_SSL_REDIRECT=False)
class CustomerInfoApiTests(TestCase):
    """`api_customer_info` feeds the customer panel on sales/create/."""

    def setUp(self):
        self.user = User.objects.create_user(username='cashier', password='password')
        self.user.user_permissions.add(Permission.objects.get(codename='view_customer'))
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(
            name='Hasan Ali',
            phone='01711111111',
            total_due=Decimal('250.00'),
        )

    def url(self):
        return reverse('customers:api_customer_info', args=[self.customer.pk])

    def test_returns_phone_and_outstanding_due(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload['phone'], '01711111111')
        self.assertEqual(Decimal(payload['total_due']), Decimal('250.00'))
        self.assertEqual(Decimal(payload['opening_balance']), Decimal('0.00'))
        self.assertEqual(payload['opening_balance_date'], self.customer.opening_balance_date.isoformat())

    def test_loyalty_absent_while_the_model_has_no_scheme(self):
        """No loyalty column today, so the key must not appear at all.

        The sale screen keys its badge off presence: an empty string or a null
        here would render a blank loyalty row for every customer.
        """
        payload = self.client.get(self.url()).json()
        self.assertNotIn('loyalty', payload)

    def test_loyalty_is_reported_once_the_model_grows_the_fields(self):
        """Future-ready: a migration adding these fields needs no view change."""
        self.customer.loyalty_tier = 'Gold'
        self.customer.loyalty_points = 1200

        self.assertEqual(
            _customer_loyalty(self.customer),
            {'tier': 'Gold', 'points': '1200'},
        )

    def test_loyalty_omits_a_tier_that_is_set_but_blank(self):
        self.customer.loyalty_tier = ''

        self.assertIsNone(_customer_loyalty(self.customer))

    def test_zero_points_are_still_reported(self):
        """0 is a real balance, not a missing value."""
        self.customer.loyalty_points = 0

        self.assertEqual(_customer_loyalty(self.customer), {'points': '0'})

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 302)


@override_settings(SECURE_SSL_REDIRECT=False)
class OpeningBalanceViewTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name='Legacy Customer', phone='01733333333')
        self.permission = Permission.objects.get(codename='set_opening_balance')
        self.user = User.objects.create_user(username='manager', password='password')
        self.user.user_permissions.add(self.permission)
        self.client.force_login(self.user)
        self.url = reverse('customers:opening_balance_set', args=[self.customer.pk])

    def test_authorized_user_can_get_and_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

        response = self.client.post(self.url, {
            'opening_balance': '350.00',
            'opening_balance_date': '2024-12-31',
        })

        self.assertRedirects(response, reverse('customers:customer_detail', args=[self.customer.pk]))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.opening_balance, Decimal('350.00'))
        self.assertEqual(self.customer.total_due, Decimal('350.00'))
        audit = AuditLog.objects.get(model_name='Customer', object_id=self.customer.pk)
        self.assertEqual(audit.action, 'UPDATE')
        self.assertEqual(audit.changes['opening_balance']['old'], '0.00')
        self.assertEqual(audit.changes['opening_balance']['new'], '350.00')

    def test_unauthorized_user_is_redirected(self):
        self.user.user_permissions.clear()
        self.user = User.objects.get(pk=self.user.pk)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('core:unauthorized'))

    def test_invalid_post_does_not_change_customer_or_create_audit(self):
        response = self.client.post(self.url, {
            'opening_balance': '-1.00',
            'opening_balance_date': '2024-12-31',
        })
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.opening_balance, Decimal('0.00'))
        self.assertFalse(AuditLog.objects.exists())

    def test_group_setup_excludes_cashier_and_includes_manager_and_admin(self):
        call_command('setup_groups', verbosity=0)
        for group_name in ('Manager', 'Admin'):
            self.assertTrue(
                Group.objects.get(name=group_name).permissions.filter(pk=self.permission.pk).exists()
            )
        self.assertFalse(
            Group.objects.get(name='Cashier').permissions.filter(pk=self.permission.pk).exists()
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class CustomerStatementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='statement-admin', password='password')
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(
            name='Statement Customer',
            phone='01744444444',
            opening_balance=Decimal('100.00'),
            opening_balance_date=date(2025, 1, 1),
        )
        self.sale = Sale.objects.create(
            customer=self.customer,
            sale_date=date(2025, 1, 10),
            subtotal=Decimal('80.00'),
            total_amount=Decimal('80.00'),
            total_cost=Decimal('40.00'),
            status=Sale.Status.COMPLETED,
            created_by=self.user,
        )
        self.payment = Payment.objects.create(
            customer=self.customer,
            amount=Decimal('50.00'),
            received_by=self.user,
        )
        Payment.objects.filter(pk=self.payment.pk).update(
            payment_date=timezone.make_aware(datetime(2025, 1, 15, 9, 0))
        )
        self.sale_return = SaleReturn.objects.create(
            sale=self.sale,
            return_date=timezone.make_aware(datetime(2025, 1, 12, 9, 0)),
            reason='Refund',
            refund_amount=Decimal('20.00'),
            created_by=self.user,
        )
        self.customer.recalculate_balance()
        self.url = reverse('customers:customer_statement', args=[self.customer.pk])

    def test_unfiltered_statement_has_opening_sale_refund_and_payment(self):
        response = self.client.get(self.url)
        transactions = response.context['transactions']
        self.assertEqual(
            [entry['type'] for entry in transactions],
            ['Opening Balance', 'Invoice', 'Refund', 'Payment'],
        )
        self.assertEqual(response.context['opening_balance'], Decimal('0'))
        self.assertEqual(response.context['closing_balance'], Decimal('150.00'))
        self.assertEqual(self.customer.total_due, Decimal('150.00'))

    def test_date_range_carries_opening_and_prior_transactions_without_duplication(self):
        response = self.client.get(self.url, {
            'date_from': '2025-01-12',
            'date_to': '2025-01-31',
        })
        transactions = response.context['transactions']
        self.assertEqual(response.context['opening_balance'], Decimal('180.00'))
        self.assertEqual([entry['type'] for entry in transactions], ['Refund', 'Payment'])
        self.assertEqual(response.context['closing_balance'], Decimal('150.00'))

    def test_opening_row_appears_when_effective_date_is_inside_window(self):
        response = self.client.get(self.url, {
            'date_from': '2025-01-01',
            'date_to': '2025-01-05',
        })
        self.assertEqual(response.context['opening_balance'], Decimal('0'))
        self.assertEqual(
            [entry['type'] for entry in response.context['transactions']],
            ['Opening Balance'],
        )

    def test_zero_opening_balance_does_not_add_statement_row(self):
        self.customer.opening_balance = Decimal('0.00')
        self.customer.save(update_fields=['opening_balance'])

        response = self.client.get(self.url, {
            'date_from': '2025-01-01',
            'date_to': '2025-01-05',
        })

        self.assertNotIn(
            'Opening Balance',
            [entry['type'] for entry in response.context['transactions']],
        )
