from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from django.utils import timezone
from django.urls import reverse

from apps.inventory.models import Category, Brand, Product, ProductStock
from apps.warehouse.models import Warehouse

class ReportsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        
        self.warehouse = Warehouse.objects.create(name='Shop Warehouse', code='SHOP', is_shop=True)
        self.category = Category.objects.create(name='Electronics')
        
        self.product1 = Product.objects.create(
            sku='PHONE-X',
            category=self.category,
            default_selling_price=Decimal('1000.00'),
            average_cost=Decimal('500.00'),
            total_stock=20
        )
        ProductStock.objects.create(product=self.product1, warehouse=self.warehouse, quantity=20)
        
        self.product2 = Product.objects.create(
            sku='PHONE-Y',
            category=self.category,
            default_selling_price=Decimal('800.00'),
            average_cost=Decimal('400.00'),
            total_stock=0
        )
        ProductStock.objects.create(product=self.product2, warehouse=self.warehouse, quantity=0)

    def test_stock_report_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('stock_report'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('stock_summary', response.context)
        self.assertEqual(response.context['totals']['total_value'], Decimal('10000.00'))
        self.assertEqual(response.context['totals']['total_items'], 20)

    def test_dead_stock_report_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dead_stock_report'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('dead_stock', response.context)
        
    def test_low_stock_report_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('stock_report'), {'stock_filter': 'low'})
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('stock_summary', response.context)
