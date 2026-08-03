"""Guard-rail tests for the transfer_create POST contract.

transfer_create reads `request.POST.getlist('items')` where each entry is a
JSON string for one line. These lock the contract (and the stock-safety
behaviors: source-warehouse debit, insufficient-stock rejection, merged
duplicate lines) before any item-builder JS refactor.
"""
import json

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from apps.inventory.models import Category, Brand, Product, ProductStock
from apps.warehouse.models import Warehouse, StockTransfer, StockTransferItem


class TransferCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='truser', password='password')
        self.source = Warehouse.objects.create(name='Source', code='SRC')
        self.dest = Warehouse.objects.create(name='Dest', code='DST')
        self.category = Category.objects.create(name='Cat')
        self.brand = Brand.objects.create(name='Br')
        self.product = Product.objects.create(
            sku='TR-1', category=self.category, brand=self.brand,
            default_selling_price=Decimal('100.00'), average_cost=Decimal('40.00'),
        )
        ProductStock.objects.create(product=self.product, warehouse=self.source, quantity=20)
        self.product.update_total_stock()
        self.client.force_login(self.user)

    def _post(self, items):
        return self.client.post(reverse('warehouse:transfer_create'), {
            'source_warehouse': self.source.id,
            'destination_warehouse': self.dest.id,
            'transfer_date': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'notes': 'test',
            'items': [json.dumps(i) for i in items],
        })

    def test_transfer_create_debits_source(self):
        resp = self._post([{'product_id': self.product.id, 'quantity': '5'}])
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(StockTransfer.objects.count(), 1)
        transfer = StockTransfer.objects.first()
        item = StockTransferItem.objects.get(transfer=transfer)
        self.assertEqual(item.quantity, 5)
        self.assertEqual(item.product, self.product)

    def test_transfer_create_merges_duplicate_lines(self):
        # Two lines for the same product must be merged before the stock check.
        resp = self._post([
            {'product_id': self.product.id, 'quantity': '5'},
            {'product_id': self.product.id, 'quantity': '3'},
        ])
        self.assertEqual(resp.status_code, 302)
        transfer = StockTransfer.objects.first()
        items = StockTransferItem.objects.filter(transfer=transfer)
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.first().quantity, 8)

    def test_transfer_create_rejects_insufficient_stock(self):
        resp = self._post([{'product_id': self.product.id, 'quantity': '999'}])
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(StockTransfer.objects.count(), 0)
        stock = ProductStock.objects.get(product=self.product, warehouse=self.source)
        self.assertEqual(stock.quantity, 20)

    def test_transfer_create_rejects_malformed_items(self):
        resp = self.client.post(reverse('warehouse:transfer_create'), {
            'source_warehouse': self.source.id,
            'destination_warehouse': self.dest.id,
            'transfer_date': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'items': ['{not json'],
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(StockTransfer.objects.count(), 0)
