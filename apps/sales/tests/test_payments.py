from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from apps.sales.models import Sale
from apps.customers.models import Customer, Payment

class PaymentStatusTests(TestCase):
    def setUp(self):
        # Create a user
        self.user = User.objects.create_user(username='testuser', password='password')
        
        # Create a customer
        self.customer = Customer.objects.create(name="Test Customer")
        
        # Create a sale
        self.sale = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.localdate(),
            subtotal=Decimal('100.00'),
            discount_amount=Decimal('0.00'),
            total_amount=Decimal('100.00'),
            paid_amount=Decimal('0.00'),
            total_cost=Decimal('50.00'),
            status='completed',
            created_by=self.user
        )

    def test_unpaid_status(self):
        """Verify sale status is unpaid when 0 payments exist."""
        self.assertEqual(self.sale.payment_status, 'unpaid')
        self.assertEqual(self.sale.paid_amount, Decimal('0.00'))

    def test_partial_status(self):
        """Verify status becomes partial when a payment is created for less than total."""
        Payment.objects.create(
            sale=self.sale,
            customer=self.customer,
            amount=Decimal('40.00'),
            received_by=self.user
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, 'partial')
        self.assertEqual(self.sale.paid_amount, Decimal('40.00'))

    def test_paid_status(self):
        """Verify status becomes paid when payment equals total amount."""
        Payment.objects.create(
            sale=self.sale,
            customer=self.customer,
            amount=Decimal('100.00'),
            received_by=self.user
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, 'paid')
        self.assertEqual(self.sale.paid_amount, Decimal('100.00'))

    def test_payment_update(self):
        """Verify status shifts if an existing payment amount is changed."""
        payment = Payment.objects.create(
            sale=self.sale,
            customer=self.customer,
            amount=Decimal('100.00'),
            received_by=self.user
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, 'paid')
        
        # Update payment
        payment.amount = Decimal('50.00')
        payment.save()
        
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, 'partial')
        self.assertEqual(self.sale.paid_amount, Decimal('50.00'))

    def test_payment_deletion(self):
        """Verify status reverts if the only payment is deleted."""
        payment = Payment.objects.create(
            sale=self.sale,
            customer=self.customer,
            amount=Decimal('100.00'),
            received_by=self.user
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, 'paid')
        
        # Delete payment
        payment.delete()
        
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, 'unpaid')
        self.assertEqual(self.sale.paid_amount, Decimal('0.00'))

    def test_overpaid_status(self):
        """Verify behavior if a payment exceeds the total amount."""
        Payment.objects.create(
            sale=self.sale,
            customer=self.customer,
            amount=Decimal('150.00'),
            received_by=self.user
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, 'paid')
        self.assertEqual(self.sale.paid_amount, Decimal('150.00'))

    def test_multiple_payments(self):
        """Verify multiple payments sum up correctly and trigger status changes."""
        # First payment
        Payment.objects.create(
            sale=self.sale,
            customer=self.customer,
            amount=Decimal('30.00'),
            received_by=self.user
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, 'partial')
        self.assertEqual(self.sale.paid_amount, Decimal('30.00'))
        
        # Second payment
        Payment.objects.create(
            sale=self.sale,
            customer=self.customer,
            amount=Decimal('70.00'),
            received_by=self.user
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, 'paid')
        self.assertEqual(self.sale.paid_amount, Decimal('100.00'))
