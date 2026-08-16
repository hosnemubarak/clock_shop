from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from apps.customers.models import Customer, Payment
from apps.sales.models import Sale, SaleReturn


class CustomerBalanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='balance-user')
        self.customer = Customer.objects.create(
            name='Balance Customer',
            phone='01711111111',
            opening_balance_date=date(2025, 1, 1),
        )

    def create_sale(self, amount=Decimal('100.00')):
        return Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.localdate(),
            total_amount=amount,
            subtotal=amount,
            total_cost=Decimal('50.00'),
            status=Sale.Status.COMPLETED,
            created_by=self.user,
        )

    def test_zero_opening_balance_preserves_existing_formula(self):
        self.create_sale()
        Payment.objects.create(
            customer=self.customer,
            amount=Decimal('25.00'),
            received_by=self.user,
        )

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_purchases, Decimal('100.00'))
        self.assertEqual(self.customer.total_paid, Decimal('25.00'))
        self.assertEqual(self.customer.total_due, Decimal('75.00'))

    def test_opening_balance_only_changes_total_due(self):
        self.customer.opening_balance = Decimal('250.00')
        self.customer.save(update_fields=['opening_balance'])
        self.customer.recalculate_balance()

        self.assertEqual(self.customer.total_purchases, Decimal('0.00'))
        self.assertEqual(self.customer.total_paid, Decimal('0.00'))
        self.assertEqual(self.customer.total_due, Decimal('250.00'))

    def test_sale_payment_and_refund_include_opening_balance(self):
        self.customer.opening_balance = Decimal('50.00')
        self.customer.save(update_fields=['opening_balance'])
        sale = self.create_sale()
        Payment.objects.create(
            customer=self.customer,
            sale=sale,
            amount=Decimal('80.00'),
            received_by=self.user,
        )
        SaleReturn.objects.create(
            sale=sale,
            return_date=timezone.now(),
            reason='Refund',
            refund_amount=Decimal('20.00'),
            created_by=self.user,
        )

        self.customer.recalculate_balance()
        self.assertEqual(self.customer.total_purchases, Decimal('100.00'))
        self.assertEqual(self.customer.total_paid, Decimal('60.00'))
        self.assertEqual(self.customer.total_due, Decimal('90.00'))

    def test_defaults_are_zero_and_local_date(self):
        customer = Customer.objects.create(name='Default Customer', phone='01711111112')
        self.assertEqual(customer.opening_balance, Decimal('0.00'))
        self.assertEqual(customer.opening_balance_date, timezone.localdate())
