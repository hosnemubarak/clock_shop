"""Tests for the sale returns feature (return_create): restock behavior,
returnable-quantity enforcement, and refund recording.
"""
from decimal import Decimal

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer, Payment
from apps.inventory.models import Category, Brand, Product, ProductStock
from apps.warehouse.models import Warehouse
from apps.sales.models import Sale, SaleItem, SaleReturn, SaleReturnItem


class SaleReturnTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ret', password='password')
        self.warehouse = Warehouse.objects.create(name='Shop', code='SHOP', is_shop=True)
        self.category = Category.objects.create(name='Cat')
        self.brand = Brand.objects.create(name='Br')
        self.product = Product.objects.create(
            sku='RT-1', category=self.category, brand=self.brand,
            default_selling_price=Decimal('100.00'), average_cost=Decimal('40.00'),
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=8)
        self.product.update_total_stock()
        self.sale = Sale.objects.create(
            sale_date=timezone.localdate(), status='completed',
            total_amount=Decimal('200.00'), created_by=self.user,
        )
        self.item = SaleItem.objects.create(
            sale=self.sale, product=self.product, warehouse=self.warehouse,
            quantity=2, unit_price=Decimal('100.00'), cost_price=Decimal('40.00'),
        )
        self.client.force_login(self.user)

    def _post(self, qty, refund='100.00', reason='defective'):
        return self.client.post(
            reverse('sales:return_create') + f'?sale={self.sale.pk}',
            {
                'sale': self.sale.pk,
                'return_date': timezone.now().strftime('%Y-%m-%dT%H:%M'),
                'refund_amount': refund,
                'reason': reason,
                f'qty_{self.item.id}': str(qty),
            },
        )

    def test_return_restocks_and_records(self):
        resp = self._post(1)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SaleReturn.objects.count(), 1)
        self.assertEqual(SaleReturnItem.objects.count(), 1)
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, 9)  # 8 + 1 returned
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 9)
        sr = SaleReturn.objects.first()
        self.assertEqual(sr.refund_amount, Decimal('100.00'))

    def test_cannot_return_more_than_sold(self):
        resp = self._post(5)  # only 2 sold
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SaleReturn.objects.count(), 0)
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, 8)

    def test_cannot_exceed_remaining_after_partial_return(self):
        self._post(1)  # 1 returned, 1 remaining
        resp = self._post(2)  # requesting 2 more should fail
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SaleReturn.objects.count(), 1)  # no second return created
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, 9)

    def test_reason_required(self):
        resp = self._post(1, reason='')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SaleReturn.objects.count(), 0)

    def test_non_completed_sale_rejected(self):
        self.sale.status = 'cancelled'
        self.sale.save(update_fields=['status'])
        resp = self._post(1)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SaleReturn.objects.count(), 0)

    def test_return_reduces_sale_total_by_goods_value(self):
        # Return 1 of 2 units at 100 each -> sale total drops 200 -> 100.
        self._post(1, refund='100.00')
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.total_amount, Decimal('100.00'))

    def test_refund_moves_customer_ledger_to_even(self):
        # Attach a customer, fully pay the 200 sale, then return 1 unit and
        # refund 100. Net: goods owed 100, net cash 200 - 100 = 100 -> due 0.
        customer = Customer.objects.create(name='Ledger', phone='+8801710000001')
        self.sale.customer = customer
        self.sale.save(update_fields=['customer'])
        Payment.objects.create(
            customer=customer, sale=self.sale, amount=Decimal('200.00'),
            payment_method='cash', received_by=self.user,
        )
        customer.refresh_from_db()
        self.assertEqual(customer.total_due, Decimal('0.00'))  # paid in full

        self._post(1, refund='100.00')

        self.sale.refresh_from_db()
        customer.refresh_from_db()
        self.assertEqual(self.sale.total_amount, Decimal('100.00'))
        self.assertEqual(self.sale.paid_amount, Decimal('100.00'))  # 200 - 100 refund
        # 100 goods owed - (200 paid - 100 refunded) = 0. Not negative/overpaid.
        self.assertEqual(customer.total_due, Decimal('0.00'))

    def test_cancel_blocked_when_sale_has_returns(self):
        # Return 1 unit (stock 8 -> 9), then attempt to cancel the sale.
        self._post(1, refund='0.00')
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, 9)

        resp = self.client.post(reverse('sales:sale_cancel', args=[self.sale.pk]))
        self.assertEqual(resp.status_code, 302)
        self.sale.refresh_from_db()
        # Cancel must be refused so the returned unit is not restocked twice.
        self.assertNotEqual(self.sale.status, 'cancelled')
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 9)  # unchanged, no double restock

    def test_return_reduces_total_cost_and_keeps_profit_correct(self):
        # Book COGS on the sale (2 units @ 40 cost). profit = 200 - 80 = 120.
        self.sale.total_cost = Decimal('80.00')
        self.sale.save(update_fields=['total_cost'])
        self.assertEqual(self.sale.profit, Decimal('120.00'))

        self._post(1, refund='100.00')  # return 1 unit (cost 40, price 100)

        self.sale.refresh_from_db()
        # Cost of the returned unit leaves the sale so profit stays honest.
        self.assertEqual(self.sale.total_amount, Decimal('100.00'))
        self.assertEqual(self.sale.total_cost, Decimal('40.00'))
        self.assertEqual(self.sale.profit, Decimal('60.00'))  # 100 - 40

    def test_paid_amount_survives_later_payment_recompute(self):
        # Fully pay the 200 sale, refund 100 on a return, then add another
        # payment. The refund must not be resurrected by the payment recompute.
        customer = Customer.objects.create(name='Durable', phone='+8801710000002')
        self.sale.customer = customer
        self.sale.save(update_fields=['customer'])
        Payment.objects.create(
            customer=customer, sale=self.sale, amount=Decimal('200.00'),
            payment_method='cash', received_by=self.user,
        )
        self._post(1, refund='100.00')  # total 100, paid 100 after refund

        self.sale.refresh_from_db()
        self.assertEqual(self.sale.paid_amount, Decimal('100.00'))

        # A later payment event triggers recalculate_paid_amount; the refund
        # (100) must still be netted out: paid = (200 + 25) - 100 = 125.
        Payment.objects.create(
            customer=customer, sale=self.sale, amount=Decimal('25.00'),
            payment_method='cash', received_by=self.user,
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.paid_amount, Decimal('125.00'))
