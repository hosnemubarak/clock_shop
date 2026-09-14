"""
Tests for sale returns: financial algorithm, stock restoration,
guards, race protection, and the return views.

Run with: python manage.py test apps.sales -v2
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLog
from apps.customers.models import Customer, Payment
from apps.inventory.models import Batch, Brand, Category, Product
from apps.warehouse.models import Warehouse

from .models import Sale, SaleItem, SaleReturn, SaleReturnItem, DocumentSequence


class SaleReturnTestBase(TestCase):
    """Shared fixtures and helpers for return tests."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.category = Category.objects.create(name='Clocks')
        self.brand = Brand.objects.create(name='TestBrand')
        self.warehouse = Warehouse.objects.create(name='Main Shop', code='SHOP1', is_shop=True)

        self.product_a = Product.objects.create(
            sku='CLK-001', category=self.category, brand=self.brand,
            default_selling_price=Decimal('100'),
        )
        self.product_b = Product.objects.create(
            sku='CLK-002', category=self.category, brand=self.brand,
            default_selling_price=Decimal('50'),
        )
        self.batch_a = Batch.objects.create(
            product=self.product_a, warehouse=self.warehouse,
            buy_price=Decimal('60'), initial_quantity=20, quantity=20,
            purchase_date=date.today(),
        )
        self.batch_b = Batch.objects.create(
            product=self.product_b, warehouse=self.warehouse,
            buy_price=Decimal('30'), initial_quantity=10, quantity=10,
            purchase_date=date.today(),
        )
        self.customer = Customer.objects.create(name='John Doe', phone='01234567890')

    def create_sale(self, customer=None, lines=None,
                    discount_amount='0', tax_amount='0'):
        """Create a completed sale directly (mirrors sale_create logic)."""
        sale = Sale.objects.create(
            customer=customer,
            sale_date=timezone.now(),
            status='completed',
            discount_amount=Decimal(discount_amount),
            tax_amount=Decimal(tax_amount),
            created_by=self.user,
        )
        subtotal = Decimal('0')
        total_cost = Decimal('0')
        for line in lines:
            if line.get('is_custom'):
                item = SaleItem.objects.create(
                    sale=sale,
                    quantity=line['quantity'],
                    unit_price=Decimal(line['unit_price']),
                    cost_price=Decimal('0'),
                    discount=Decimal(line.get('discount', '0')),
                    is_custom=True,
                    custom_description=line.get('custom_description', 'Custom Item'),
                )
            else:
                batch = line['batch']
                item = SaleItem.objects.create(
                    sale=sale,
                    product=line['product'],
                    batch=batch,
                    quantity=line['quantity'],
                    unit_price=Decimal(line['unit_price']),
                    cost_price=batch.buy_price,
                    discount=Decimal(line.get('discount', '0')),
                )
                batch.quantity -= line['quantity']
                batch.save()
                line['product'].update_total_stock()
            subtotal += item.total_price
            total_cost += item.total_cost

        sale.subtotal = subtotal
        sale.total_cost = total_cost
        sale.total_amount = subtotal - sale.discount_amount + sale.tax_amount
        sale.save()
        if customer:
            customer.recalculate_balance()
        return sale

    def create_return(self, sale, lines, reason='Customer return', process=True):
        """
        Create a return and its items, then process it.
        `lines` is a list of (sale_item, quantity) tuples.
        """
        with transaction.atomic():
            sale_return = SaleReturn.objects.create(
                sale=sale,
                return_date=timezone.now(),
                reason=reason,
                refund_amount=Decimal('0.00'),
                status='pending',
                created_by=self.user,
            )
            for sale_item, qty in lines:
                SaleReturnItem.objects.create(
                    sale_return=sale_return,
                    sale_item=sale_item,
                    quantity=qty,
                    unit_price=sale_item.unit_price,
                    cost_price=sale_item.cost_price,
                )
            if process:
                sale_return.process_return()
        sale_return.refresh_from_db()
        return sale_return

    def make_worked_example_sale(self):
        """
        The canonical worked example:
        subtotal 1090 (A: 10x100, B: 2x50 with -10 item discount),
        invoice discount 100, tax 50 -> total 1040.
        """
        return self.create_sale(
            customer=self.customer,
            lines=[
                {'product': self.product_a, 'batch': self.batch_a,
                 'quantity': 10, 'unit_price': '100'},
                {'product': self.product_b, 'batch': self.batch_b,
                 'quantity': 2, 'unit_price': '50', 'discount': '10'},
            ],
            discount_amount='100', tax_amount='50',
        )


class SaleReturnProcessingTests(SaleReturnTestBase):

    def test_document_numbering(self):
        """Invoice and return numbers are short global running numbers."""
        DocumentSequence.objects.filter(key='invoice').update(value=10000)
        DocumentSequence.objects.filter(key='return').update(value=10000)

        first = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 1, 'unit_price': '100'},
        ])
        second = self.create_sale(lines=[
            {'product': self.product_b, 'batch': self.batch_b,
             'quantity': 1, 'unit_price': '50'},
        ])
        self.assertEqual(first.invoice_number, 'INV10001')
        self.assertEqual(second.invoice_number, 'INV10002')

        item = first.items.first()
        sale_return = self.create_return(first, [(item, 1)])
        self.assertEqual(sale_return.return_number, 'RET10001')

    def test_numbering_coexists_with_legacy_format(self):
        """Legacy long numbers never collide with the new short format."""
        DocumentSequence.objects.filter(key='invoice').update(value=10000)

        legacy = Sale.objects.create(
            invoice_number='INV202609140006',
            sale_date=timezone.now(),
            status='completed',
            created_by=self.user,
        )
        new_sale = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 1, 'unit_price': '100'},
        ])
        self.assertNotEqual(legacy.invoice_number, new_sale.invoice_number)
        self.assertEqual(new_sale.invoice_number, 'INV10001')
        self.assertEqual(Sale.objects.filter(
            invoice_number=new_sale.invoice_number
        ).count(), 1)

    def test_document_sequence_unique_and_atomic(self):
        """Concurrent number issuance never yields duplicates."""
        from threading import Thread, Lock

        results = []
        results_lock = Lock()

        def issue():
            value = DocumentSequence.next_value('invoice')
            with results_lock:
                results.append(value)

        try:
            threads = [Thread(target=issue) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            # Threads commit on their own connections; restore the seed
            DocumentSequence.objects.filter(key='invoice').update(value=10000)

        self.assertEqual(len(results), 10)
        self.assertEqual(len(set(results)), 10, 'Duplicate numbers issued')
        self.assertEqual(sorted(results), list(range(10001, 10011)))

    def test_full_return_registered_customer(self):
        sale = self.make_worked_example_sale()
        original_total = sale.total_amount
        self.assertEqual(original_total, Decimal('1040'))

        Payment.objects.create(
            customer=self.customer, sale=sale,
            amount=Decimal('400'), received_by=self.user,
        )
        sale.paid_amount = Decimal('400')
        sale.update_payment_status()

        items = list(sale.items.all())
        sale_return = self.create_return(sale, [(items[0], 10), (items[1], 2)])

        sale.refresh_from_db()
        self.batch_a.refresh_from_db()
        self.batch_b.refresh_from_db()
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()

        # Stock fully restored
        self.assertEqual(self.batch_a.quantity, 20)
        self.assertEqual(self.batch_b.quantity, 10)
        self.assertEqual(self.product_a.total_stock, 20)
        self.assertEqual(self.product_b.total_stock, 10)

        # All sale totals snapped to zero
        self.assertEqual(sale.subtotal, Decimal('0'))
        self.assertEqual(sale.discount_amount, Decimal('0'))
        self.assertEqual(sale.tax_amount, Decimal('0'))
        self.assertEqual(sale.total_amount, Decimal('0'))
        self.assertEqual(sale.total_cost, Decimal('0'))

        # Sum of refunds equals the original total (no rounding dust)
        self.assertEqual(sale.total_returned_amount, original_total)
        self.assertTrue(sale.has_returns)

        # The 400 payment was fully reversed (refunded to the customer)
        self.assertEqual(sale_return.payment_refund_amount, Decimal('400'))

        # Customer figures recomputed from source: net paid is zero because
        # the payment was refunded, so no credit is carried
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_purchases, Decimal('0'))
        self.assertEqual(self.customer.total_paid, Decimal('0'))
        self.assertEqual(self.customer.total_due, Decimal('0'))
        self.assertEqual(sale.payment_status, 'paid')

    def test_partial_return_single_item(self):
        sale = self.make_worked_example_sale()

        item_a = sale.items.first()
        sale_return = self.create_return(sale, [(item_a, 5)])

        sale.refresh_from_db()
        self.assertEqual(sale_return.refund_amount, Decimal('477.28'))
        self.assertEqual(sale.subtotal, Decimal('590'))
        self.assertEqual(sale.discount_amount, Decimal('54.55'))
        self.assertEqual(sale.tax_amount, Decimal('27.27'))
        self.assertEqual(sale.total_amount, Decimal('562.72'))
        self.assertEqual(sale.total_cost, Decimal('360'))

        # Remaining quantities tracked per item
        item_a.refresh_from_db()
        self.assertEqual(item_a.returned_quantity, 5)
        self.assertEqual(item_a.returnable_quantity, 5)
        item_b = list(sale.items.all())[1]
        self.assertEqual(item_b.returned_quantity, 0)

        # Stock partially restored
        self.batch_a.refresh_from_db()
        self.assertEqual(self.batch_a.quantity, 15)

    def test_partial_return_multiple_items(self):
        sale = self.make_worked_example_sale()

        item_a, item_b = list(sale.items.all())
        sale_return = self.create_return(sale, [(item_a, 3), (item_b, 1)])

        sale.refresh_from_db()
        # line_gross 350, item disc share 5.00, inv disc share 31.82, tax 15.91
        self.assertEqual(sale_return.refund_amount, Decimal('329.09'))
        self.assertEqual(sale.subtotal, Decimal('745'))
        self.assertEqual(sale.discount_amount, Decimal('68.18'))
        self.assertEqual(sale.tax_amount, Decimal('34.09'))
        self.assertEqual(sale.total_amount, Decimal('710.91'))
        self.assertEqual(sale.total_cost, Decimal('450'))

        self.batch_a.refresh_from_db()
        self.batch_b.refresh_from_db()
        self.assertEqual(self.batch_a.quantity, 13)
        self.assertEqual(self.batch_b.quantity, 9)

    def test_multiple_sequential_returns(self):
        sale = self.make_worked_example_sale()
        item_a, item_b = list(sale.items.all())

        first = self.create_return(sale, [(item_a, 5)])
        sale.refresh_from_db()
        second = self.create_return(sale, [(item_a, 5), (item_b, 2)])
        sale.refresh_from_db()

        # Cumulative refunds exactly equal the original total (full-return snap)
        self.assertEqual(first.refund_amount, Decimal('477.28'))
        self.assertEqual(second.refund_amount, Decimal('562.72'))
        self.assertEqual(sale.total_returned_amount, Decimal('1040'))
        self.assertEqual(sale.total_amount, Decimal('0'))
        self.assertEqual(sale.subtotal, Decimal('0'))
        self.assertEqual(sale.total_cost, Decimal('0'))

        # Nothing left to return
        with self.assertRaises(ValidationError):
            self.create_return(sale, [(item_a, 1)])

    def test_return_exceeds_quantity_rejected(self):
        sale = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 2, 'unit_price': '100'},
        ])
        item = sale.items.first()

        with self.assertRaises(ValidationError):
            self.create_return(sale, [(item, 3)])

        self.assertEqual(SaleReturn.objects.filter(sale=sale).count(), 0)
        self.batch_a.refresh_from_db()
        self.assertEqual(self.batch_a.quantity, 18)
        sale.refresh_from_db()
        self.assertEqual(sale.total_amount, Decimal('200'))
        self.assertFalse(sale.has_returns)

    def test_return_exceeds_remaining_rejected(self):
        sale = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 10, 'unit_price': '100'},
        ])
        item = sale.items.first()

        self.create_return(sale, [(item, 4)])

        with self.assertRaises(ValidationError):
            self.create_return(sale, [(item, 7)])

        # The rejected attempt changed nothing
        self.batch_a.refresh_from_db()
        self.assertEqual(self.batch_a.quantity, 14)
        sale.refresh_from_db()
        self.assertEqual(sale.total_amount, Decimal('600'))
        item.refresh_from_db()
        self.assertEqual(item.returned_quantity, 4)

    def test_walk_in_return(self):
        sale = self.create_sale(customer=None, lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 5, 'unit_price': '100'},
        ])
        self.assertEqual(sale.total_amount, Decimal('500'))

        item = sale.items.first()
        sale_return = self.create_return(sale, [(item, 5)])

        sale.refresh_from_db()
        self.batch_a.refresh_from_db()
        self.product_a.refresh_from_db()

        self.assertEqual(sale_return.refund_amount, Decimal('500'))
        self.assertEqual(sale.total_amount, Decimal('0'))
        self.assertEqual(self.batch_a.quantity, 20)
        self.assertEqual(self.product_a.total_stock, 20)
        # No customer was involved and nothing raised
        self.assertIsNone(sale.customer)

    def test_return_stock_restoration(self):
        sale = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 6, 'unit_price': '100'},
            {'product': self.product_b, 'batch': self.batch_b,
             'quantity': 3, 'unit_price': '50'},
        ])
        item_a, item_b = list(sale.items.all())

        self.create_return(sale, [(item_a, 2), (item_b, 1)])

        self.batch_a.refresh_from_db()
        self.batch_b.refresh_from_db()
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()
        self.assertEqual(self.batch_a.quantity, 16)
        self.assertEqual(self.batch_b.quantity, 8)
        self.assertEqual(self.product_a.total_stock, 16)
        self.assertEqual(self.product_b.total_stock, 8)

    def test_return_refund_calculation(self):
        """The canonical worked example: refunds 477.28 then 562.72."""
        sale = self.make_worked_example_sale()
        item_a, item_b = list(sale.items.all())

        first = self.create_return(sale, [(item_a, 5)])
        self.assertEqual(first.refund_amount, Decimal('477.28'))

        second = self.create_return(sale, [(item_a, 5), (item_b, 2)])
        self.assertEqual(second.refund_amount, Decimal('562.72'))

        self.assertEqual(
            first.refund_amount + second.refund_amount, Decimal('1040')
        )

    def test_return_custom_item(self):
        sale = self.create_sale(lines=[
            {'is_custom': True, 'quantity': 1, 'unit_price': '500',
             'custom_description': 'Old Dues'},
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 2, 'unit_price': '100'},
        ])
        self.assertEqual(sale.total_amount, Decimal('700'))

        custom_item, stock_item = list(sale.items.all())
        sale_return = self.create_return(sale, [(custom_item, 1)])

        sale.refresh_from_db()
        self.assertEqual(sale_return.refund_amount, Decimal('500'))
        self.assertEqual(sale.total_amount, Decimal('200'))
        self.assertEqual(sale.total_cost, Decimal('120'))

        # No stock operations for custom items
        self.batch_a.refresh_from_db()
        self.assertEqual(self.batch_a.quantity, 18)

        # __str__ does not crash for custom items
        return_item = sale_return.items.first()
        self.assertIn('Old Dues', str(return_item))

    def test_overpaid_sale_return(self):
        sale = self.create_sale(customer=self.customer, lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 5, 'unit_price': '100'},
        ])
        self.assertEqual(sale.total_amount, Decimal('500'))

        Payment.objects.create(
            customer=self.customer, sale=sale,
            amount=Decimal('500'), received_by=self.user,
        )
        sale.paid_amount = Decimal('500')
        sale.update_payment_status()

        item = sale.items.first()
        sale_return = self.create_return(sale, [(item, 2)])

        sale.refresh_from_db()
        # paid_amount is NEVER touched by returns (paid == sum of payments)
        self.assertEqual(sale.paid_amount, Decimal('500'))
        self.assertEqual(sale.total_amount, Decimal('300'))
        # Raw invoice-level due is negative (over-paid), payment status stays paid
        self.assertEqual(sale.due_amount, Decimal('-200'))
        self.assertEqual(sale.payment_status, 'paid')

        # The 200 over-payment is refunded to the customer, not kept as credit:
        # customer keeps 300 of goods, net paid 300, owes nothing
        self.assertEqual(sale_return.payment_refund_amount, Decimal('200'))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_purchases, Decimal('300'))
        self.assertEqual(self.customer.total_paid, Decimal('300'))
        self.assertEqual(self.customer.total_due, Decimal('0'))

    def test_return_fully_paid_invoice_with_existing_due(self):
        """Canonical scenario: returning a fully-paid invoice must refund the
        payment, NOT deduct it from the customer's other outstanding dues."""
        # Existing unpaid invoice: 1,000 due
        self.create_sale(customer=self.customer, lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 10, 'unit_price': '100'},
        ])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_due, Decimal('1000'))

        # New invoice for 50, paid in full
        sale = self.create_sale(customer=self.customer, lines=[
            {'product': self.product_b, 'batch': self.batch_b,
             'quantity': 1, 'unit_price': '50'},
        ])
        Payment.objects.create(
            customer=self.customer, sale=sale,
            amount=Decimal('50'), received_by=self.user,
        )
        sale.paid_amount = Decimal('50')
        sale.update_payment_status()
        self.customer.recalculate_balance()
        self.assertEqual(self.customer.total_due, Decimal('1000'))

        # Full return of the paid invoice
        item = sale.items.first()
        sale_return = self.create_return(sale, [(item, 1)])

        sale.refresh_from_db()
        self.assertEqual(sale.total_amount, Decimal('0'))
        self.assertEqual(sale_return.refund_amount, Decimal('50'))
        self.assertEqual(sale_return.payment_refund_amount, Decimal('50'))

        # Due stays 1,000: the 50 payment was refunded, not credited
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_purchases, Decimal('1000'))
        self.assertEqual(self.customer.total_paid, Decimal('0'))
        self.assertEqual(self.customer.total_due, Decimal('1000'))

    def test_return_partially_paid_invoice_partial_return(self):
        """100 invoice, 60 paid, 40 returned: due drops to 0, no payment refund."""
        sale = self.create_sale(customer=self.customer, lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 10, 'unit_price': '10'},
        ])
        self.assertEqual(sale.total_amount, Decimal('100'))

        Payment.objects.create(
            customer=self.customer, sale=sale,
            amount=Decimal('60'), received_by=self.user,
        )
        sale.paid_amount = Decimal('60')
        sale.update_payment_status()
        self.customer.recalculate_balance()
        self.assertEqual(self.customer.total_due, Decimal('40'))

        item = sale.items.first()
        sale_return = self.create_return(sale, [(item, 4)])

        sale.refresh_from_db()
        self.assertEqual(sale_return.refund_amount, Decimal('40'))
        self.assertEqual(sale_return.payment_refund_amount, Decimal('0'))
        self.assertEqual(sale.total_amount, Decimal('60'))
        self.assertEqual(sale.due_amount, Decimal('0'))

        # The return settled the remaining due; the 60 payment stands
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_purchases, Decimal('60'))
        self.assertEqual(self.customer.total_paid, Decimal('60'))
        self.assertEqual(self.customer.total_due, Decimal('0'))

    def test_return_partially_paid_invoice_full_return(self):
        """100 invoice, 60 paid, fully returned: the 60 payment is refunded."""
        sale = self.create_sale(customer=self.customer, lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 10, 'unit_price': '10'},
        ])
        Payment.objects.create(
            customer=self.customer, sale=sale,
            amount=Decimal('60'), received_by=self.user,
        )
        sale.paid_amount = Decimal('60')
        sale.update_payment_status()

        item = sale.items.first()
        sale_return = self.create_return(sale, [(item, 10)])

        sale.refresh_from_db()
        self.assertEqual(sale_return.refund_amount, Decimal('100'))
        self.assertEqual(sale_return.payment_refund_amount, Decimal('60'))
        self.assertEqual(sale.total_amount, Decimal('0'))

        # Customer keeps nothing and net-pays nothing (60 refunded)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_purchases, Decimal('0'))
        self.assertEqual(self.customer.total_paid, Decimal('0'))
        self.assertEqual(self.customer.total_due, Decimal('0'))

    def test_return_unpaid_invoice(self):
        """Unpaid invoice return: due reduces by the refund, no payment refund."""
        sale = self.create_sale(customer=self.customer, lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 10, 'unit_price': '10'},
        ])
        self.assertEqual(sale.total_amount, Decimal('100'))

        item = sale.items.first()
        sale_return = self.create_return(sale, [(item, 4)])

        sale.refresh_from_db()
        self.assertEqual(sale_return.refund_amount, Decimal('40'))
        self.assertEqual(sale_return.payment_refund_amount, Decimal('0'))
        self.assertEqual(sale.total_amount, Decimal('60'))
        self.assertEqual(sale.due_amount, Decimal('60'))

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_purchases, Decimal('60'))
        self.assertEqual(self.customer.total_paid, Decimal('0'))
        self.assertEqual(self.customer.total_due, Decimal('60'))

    def test_return_fully_paid_invoice_partial_return(self):
        """100 paid in full, 40 returned: 40 payment refund, invoice settled."""
        sale = self.create_sale(customer=self.customer, lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 10, 'unit_price': '10'},
        ])
        Payment.objects.create(
            customer=self.customer, sale=sale,
            amount=Decimal('100'), received_by=self.user,
        )
        sale.paid_amount = Decimal('100')
        sale.update_payment_status()

        item = sale.items.first()
        sale_return = self.create_return(sale, [(item, 4)])

        sale.refresh_from_db()
        self.assertEqual(sale_return.refund_amount, Decimal('40'))
        self.assertEqual(sale_return.payment_refund_amount, Decimal('40'))
        self.assertEqual(sale.total_amount, Decimal('60'))
        # Raw invoice figures stay over-paid; status remains paid
        self.assertEqual(sale.due_amount, Decimal('-40'))
        self.assertEqual(sale.payment_status, 'paid')

        # Customer keeps 60 of goods, net paid 60, owes nothing
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_purchases, Decimal('60'))
        self.assertEqual(self.customer.total_paid, Decimal('60'))
        self.assertEqual(self.customer.total_due, Decimal('0'))

    def test_sequential_returns_payment_refund_telescoping(self):
        """100 paid in full, returned 40 then 60: payment refunds telescope
        so their sum equals the full paid amount, never more."""
        sale = self.create_sale(customer=self.customer, lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 10, 'unit_price': '10'},
        ])
        Payment.objects.create(
            customer=self.customer, sale=sale,
            amount=Decimal('100'), received_by=self.user,
        )
        sale.paid_amount = Decimal('100')
        sale.update_payment_status()

        item = sale.items.first()
        first = self.create_return(sale, [(item, 4)])
        second = self.create_return(sale, [(item, 6)])

        self.assertEqual(first.refund_amount, Decimal('40'))
        self.assertEqual(first.payment_refund_amount, Decimal('40'))
        self.assertEqual(second.refund_amount, Decimal('60'))
        self.assertEqual(second.payment_refund_amount, Decimal('60'))
        self.assertEqual(
            first.payment_refund_amount + second.payment_refund_amount,
            Decimal('100'),
        )

        sale.refresh_from_db()
        self.assertEqual(sale.total_amount, Decimal('0'))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_purchases, Decimal('0'))
        self.assertEqual(self.customer.total_paid, Decimal('0'))
        self.assertEqual(self.customer.total_due, Decimal('0'))

    def test_invoice_discount_tax_proration(self):
        sale = self.create_sale(
            customer=self.customer,
            lines=[
                {'product': self.product_a, 'batch': self.batch_a,
                 'quantity': 3, 'unit_price': '100'},
                {'product': self.product_b, 'batch': self.batch_b,
                 'quantity': 2, 'unit_price': '50', 'discount': '10'},
            ],
            discount_amount='10', tax_amount='5',
        )
        # subtotal 390, total 385
        self.assertEqual(sale.total_amount, Decimal('385'))

        item_a, item_b = list(sale.items.all())
        sale_return = self.create_return(sale, [(item_a, 1), (item_b, 1)])

        sale.refresh_from_db()
        # line_gross 150, item disc 5.00, inv disc 3.75, tax 1.88 (HALF_UP)
        self.assertEqual(sale_return.refund_amount, Decimal('143.13'))
        self.assertEqual(sale.discount_amount, Decimal('6.25'))
        self.assertEqual(sale.tax_amount, Decimal('3.12'))
        self.assertEqual(sale.subtotal, Decimal('245'))
        self.assertEqual(sale.total_cost, Decimal('150'))
        # Net figures stay consistent: 385 - 143.13 = 241.87
        self.assertEqual(sale.total_amount, Decimal('241.87'))

    def test_return_race_duplicate_protection(self):
        sale = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 10, 'unit_price': '100'},
        ])
        item = sale.items.first()

        # Both returns pass pre-lock validation (10 returnable) when created
        first = self.create_return(sale, [(item, 6)], process=False)
        second = self.create_return(sale, [(item, 6)], process=False)

        first.process_return()

        with self.assertRaises(ValidationError):
            with transaction.atomic():
                second.process_return()

        # The second return was rejected inside the lock: no double restore
        self.batch_a.refresh_from_db()
        self.assertEqual(self.batch_a.quantity, 16)
        sale.refresh_from_db()
        self.assertEqual(sale.total_amount, Decimal('400'))
        self.assertEqual(sale.total_returned_amount, Decimal('600'))
        second.refresh_from_db()
        self.assertEqual(second.status, 'pending')
        self.assertEqual(second.refund_amount, Decimal('0'))

    def test_cancelled_sale_no_return(self):
        sale = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 5, 'unit_price': '100'},
        ])
        sale.status = 'cancelled'
        sale.save()

        item = sale.items.first()
        with self.assertRaises(ValidationError):
            self.create_return(sale, [(item, 1)])

        # The view rejects cancelled sales as well
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(
            reverse('sale_return_create', args=[sale.pk]),
            {'reason': 'Not needed', f'return_qty_{item.pk}': '1'},
        )
        self.assertRedirects(response, reverse('sale_detail', args=[sale.pk]))
        self.assertEqual(SaleReturn.objects.filter(sale=sale).count(), 0)

    def test_cancel_sale_with_returns_blocked(self):
        sale = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 5, 'unit_price': '100'},
        ])
        item = sale.items.first()
        self.create_return(sale, [(item, 2)])

        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(
            reverse('sale_cancel', args=[sale.pk]), follow=True
        )

        sale.refresh_from_db()
        self.batch_a.refresh_from_db()
        # Sale untouched, no double stock restore
        self.assertEqual(sale.status, 'completed')
        self.assertEqual(self.batch_a.quantity, 17)
        messages_list = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('Cannot cancel a sale with returns' in m for m in messages_list))


class SaleReturnViewTests(SaleReturnTestBase):

    def test_return_create_view(self):
        sale = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 10, 'unit_price': '100'},
        ])
        item = sale.items.first()

        self.client.login(username='testuser', password='testpass123')

        # GET renders the form
        response = self.client.get(reverse('sale_return_create', args=[sale.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sales/sale_return_form.html')

        # POST processes the return
        response = self.client.post(
            reverse('sale_return_create', args=[sale.pk]),
            {'reason': 'Damaged in transit', f'return_qty_{item.pk}': '4'},
        )

        sale_return = SaleReturn.objects.get(sale=sale)
        self.assertRedirects(
            response, reverse('sale_return_detail', args=[sale_return.pk])
        )
        self.assertEqual(sale_return.status, 'completed')
        self.assertEqual(sale_return.refund_amount, Decimal('400'))
        self.assertTrue(
            AuditLog.objects.filter(
                action='SALE_RETURN', object_id=sale_return.pk
            ).exists()
        )

        sale.refresh_from_db()
        self.assertEqual(sale.total_amount, Decimal('600'))
        self.assertTrue(sale.has_returns)

        # Return detail view renders
        response = self.client.get(
            reverse('sale_return_detail', args=[sale_return.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sales/sale_return_detail.html')

    def test_return_create_view_validates_quantities(self):
        sale = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 3, 'unit_price': '100'},
        ])
        item = sale.items.first()

        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(
            reverse('sale_return_create', args=[sale.pk]),
            {'reason': 'Too many', f'return_qty_{item.pk}': '5'},
            follow=True,
        )

        self.assertEqual(SaleReturn.objects.filter(sale=sale).count(), 0)
        messages_list = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('only 3 returnable' in m for m in messages_list))

    def test_return_create_view_requires_reason_and_items(self):
        sale = self.create_sale(lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 3, 'unit_price': '100'},
        ])
        item = sale.items.first()

        self.client.login(username='testuser', password='testpass123')

        # No reason
        self.client.post(
            reverse('sale_return_create', args=[sale.pk]),
            {f'return_qty_{item.pk}': '1'},
        )
        # No items selected
        self.client.post(
            reverse('sale_return_create', args=[sale.pk]),
            {'reason': 'No items'},
        )
        self.assertEqual(SaleReturn.objects.filter(sale=sale).count(), 0)

    def test_sale_detail_with_returns(self):
        sale = self.make_worked_example_sale()
        item_a, item_b = list(sale.items.all())
        sale_return = self.create_return(sale, [(item_a, 3), (item_b, 1)])

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('sale_detail', args=[sale.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Return History')
        self.assertContains(response, sale_return.return_number)
        # "Returned" column shows returned / sold
        self.assertContains(response, '3 / 10')
        self.assertContains(response, '1 / 2')
        # Items remain returnable -> button still shown
        self.assertContains(response, 'Return Items')

    def test_sale_return_list_view(self):
        sale = self.make_worked_example_sale()
        item_a, item_b = list(sale.items.all())
        sale_return = self.create_return(sale, [(item_a, 3), (item_b, 1)])

        walk_in_sale = self.create_sale(customer=None, lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 2, 'unit_price': '100'},
        ])
        walk_in_item = walk_in_sale.items.first()
        walk_in_return = self.create_return(walk_in_sale, [(walk_in_item, 1)])

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('sale_return_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sales/sale_return_list.html')
        # Both returns listed with refund totals
        self.assertContains(response, sale_return.return_number)
        self.assertContains(response, walk_in_return.return_number)
        self.assertContains(response, '429.09')  # 329.09 + 100.00 total refunds
        self.assertContains(response, 'Walk-in')

        # Search filters by return number
        response = self.client.get(
            reverse('sale_return_list'), {'search': sale_return.return_number}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, sale_return.return_number)
        self.assertNotContains(response, walk_in_return.return_number)

        # Search filters by customer name
        response = self.client.get(
            reverse('sale_return_list'), {'search': 'John Doe'}
        )
        self.assertContains(response, sale_return.return_number)
        self.assertNotContains(response, walk_in_return.return_number)

        # Status filter
        response = self.client.get(
            reverse('sale_return_list'), {'status': 'cancelled'}
        )
        self.assertNotContains(response, sale_return.return_number)

        # Date range filter excludes everything when out of range
        response = self.client.get(
            reverse('sale_return_list'),
            {'date_from': '2020-01-01', 'date_to': '2020-01-02'},
        )
        self.assertNotContains(response, sale_return.return_number)

    def test_sale_detail_credit_and_fully_returned(self):
        sale = self.create_sale(customer=self.customer, lines=[
            {'product': self.product_a, 'batch': self.batch_a,
             'quantity': 5, 'unit_price': '100'},
        ])
        Payment.objects.create(
            customer=self.customer, sale=sale,
            amount=Decimal('500'), received_by=self.user,
        )
        sale.paid_amount = Decimal('500')
        sale.update_payment_status()

        item = sale.items.first()
        self.create_return(sale, [(item, 5)])

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('sale_detail', args=[sale.pk]))
        self.assertEqual(response.status_code, 200)
        # Negative due renders as credit, not "Due"
        self.assertContains(response, 'Credit (Overpaid)')
        self.assertNotContains(response, 'Return Items')


class ReturnReportingTests(SaleReturnTestBase):
    """Reports and customer statement are return-aware without double-counting."""

    def setUp(self):
        super().setUp()
        self.client.login(username='testuser', password='testpass123')
        self.sale = self.make_worked_example_sale()
        item_a, item_b = list(self.sale.items.all())
        # refund 329.09; sale: subtotal 745, total 710.91, cost 450
        self.sale_return = self.create_return(self.sale, [(item_a, 3), (item_b, 1)])

    def test_dashboard_profit_month_subtracts_returns(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        # Sold margin 440 (10x40 + 2x20) minus returned margin 140 (3x40 + 1x20)
        self.assertEqual(response.context['profit_month'], Decimal('300'))
        # Sale-total aggregates are already net of returns
        self.assertEqual(response.context['total_sales_month'], Decimal('710.91'))

    def test_sales_report_with_returns(self):
        response = self.client.get(reverse('sales_report'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['returns_total'], Decimal('329.09'))
        self.assertEqual(
            response.context['summary']['total_sales'], Decimal('710.91')
        )
        by_sku = {p['product__sku']: p for p in response.context['top_products']}
        self.assertEqual(by_sku['CLK-001']['total_quantity'], 7)
        self.assertEqual(by_sku['CLK-002']['total_quantity'], 1)
        self.assertEqual(by_sku['CLK-001']['total_revenue'], Decimal('700'))
        self.assertEqual(by_sku['CLK-002']['total_revenue'], Decimal('50'))

    def test_profit_report_with_returns(self):
        response = self.client.get(reverse('profit_report'))
        self.assertEqual(response.status_code, 200)
        totals = response.context['totals']
        # Sold revenue 1100 / cost 660; returned revenue 350 / cost 210
        self.assertEqual(totals['total_revenue'], Decimal('750'))
        self.assertEqual(totals['total_cost'], Decimal('450'))
        self.assertEqual(totals['total_profit'], Decimal('300'))

    def test_customer_report_with_returns(self):
        response = self.client.get(reverse('customer_report'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_returns'], Decimal('329.09'))

    def test_customer_statement_balances_with_returns(self):
        Payment.objects.create(
            customer=self.customer, sale=self.sale,
            amount=Decimal('200'), received_by=self.user,
        )
        self.customer.recalculate_balance()

        response = self.client.get(
            reverse('customer_statement', args=[self.customer.pk])
        )
        self.assertEqual(response.status_code, 200)
        transactions = response.context['transactions']
        self.assertIn('Return', [t['type'] for t in transactions])

        # Invoice debited at ORIGINAL amount, return credited: ledger balances
        total_debit = sum((t['debit'] for t in transactions), Decimal('0'))
        total_credit = sum((t['credit'] for t in transactions), Decimal('0'))
        self.customer.refresh_from_db()
        self.assertEqual(total_debit - total_credit, self.customer.total_due)
        # Net purchases 710.91 minus payment 200
        self.assertEqual(self.customer.total_due, Decimal('510.91'))

    def test_customer_statement_with_payment_refund(self):
        """Statement stays balanced when a fully-paid invoice is returned:
        the payment refund appears as a Refund debit row."""
        # A second, fully-paid invoice of 100 that gets fully returned
        sale = self.create_sale(customer=self.customer, lines=[
            {'product': self.product_b, 'batch': self.batch_b,
             'quantity': 2, 'unit_price': '50'},
        ])
        Payment.objects.create(
            customer=self.customer, sale=sale,
            amount=Decimal('100'), received_by=self.user,
        )
        sale.paid_amount = Decimal('100')
        sale.update_payment_status()
        item = sale.items.first()
        self.create_return(sale, [(item, 2)])

        response = self.client.get(
            reverse('customer_statement', args=[self.customer.pk])
        )
        self.assertEqual(response.status_code, 200)
        transactions = response.context['transactions']
        types = [t['type'] for t in transactions]
        self.assertIn('Refund', types)

        # Return row credits the refund; Refund row debits the payment refund
        refund_rows = [t for t in transactions if t['type'] == 'Refund']
        self.assertEqual(len(refund_rows), 1)
        self.assertEqual(refund_rows[0]['debit'], Decimal('100'))
        self.assertEqual(refund_rows[0]['credit'], Decimal('0'))

        # Ledger balances exactly against the recomputed customer due:
        # worked sale net 710.91 unpaid + returned invoice net 0
        total_debit = sum((t['debit'] for t in transactions), Decimal('0'))
        total_credit = sum((t['credit'] for t in transactions), Decimal('0'))
        self.customer.refresh_from_db()
        self.assertEqual(total_debit - total_credit, self.customer.total_due)
        self.assertEqual(self.customer.total_due, Decimal('710.91'))
