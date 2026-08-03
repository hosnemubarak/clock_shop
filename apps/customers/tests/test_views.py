"""Tests for the customer API endpoints the sale screen depends on."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.customers.models import Customer
from apps.customers.views import _customer_loyalty


class CustomerInfoApiTests(TestCase):
    """`api_customer_info` feeds the customer panel on sales/create/."""

    def setUp(self):
        self.user = User.objects.create_user(username='cashier', password='password')
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
