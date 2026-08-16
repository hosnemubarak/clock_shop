from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.customers.forms import OpeningBalanceForm
from apps.customers.models import Customer


class OpeningBalanceFormTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name='Form Customer', phone='01722222222')

    def form(self, amount, effective_date='2025-01-15'):
        return OpeningBalanceForm(
            {'opening_balance': amount, 'opening_balance_date': effective_date},
            instance=self.customer,
        )

    def test_accepts_zero_and_positive_amounts(self):
        for amount in ('0', '125.50'):
            with self.subTest(amount=amount):
                form = self.form(amount)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data['opening_balance'], Decimal(amount))
                self.assertEqual(form.cleaned_data['opening_balance_date'], date(2025, 1, 15))

    def test_rejects_negative_invalid_and_missing_values(self):
        cases = [('-0.01', '2025-01-15'), ('invalid', '2025-01-15'), ('10', '')]
        for amount, effective_date in cases:
            with self.subTest(amount=amount, effective_date=effective_date):
                self.assertFalse(self.form(amount, effective_date).is_valid())
