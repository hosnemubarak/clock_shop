from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from django.utils import timezone
from django.urls import reverse
from django.test import override_settings
import json

from apps.inventory.models import Category, Brand, Product, ProductStock
from apps.warehouse.models import Warehouse
from apps.sales.models import Sale, SaleItem
from apps.customers.models import Customer

class SalesTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        
        self.warehouse = Warehouse.objects.create(name='Shop Warehouse', code='SHOP', is_shop=True)
        self.category = Category.objects.create(name='Electronics')
        
        self.product = Product.objects.create(
            sku='PHONE-X',
            category=self.category,
            default_selling_price=Decimal('1000.00'),
            average_cost=Decimal('500.00'),
            total_stock=20
        )
        
        # Add initial stock
        ProductStock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=20
        )
        
        self.customer = Customer.objects.create(
            name='Test Customer',
            phone='1234567890'
        )

    @override_settings(DEBUG=True)
    def test_sale_creation(self):
        self.client.force_login(self.user)
        
        items_data = [
            json.dumps({
                'product_id': self.product.id,
                'warehouse_id': self.warehouse.id,
                'quantity': '2',
                'unit_price': '1000.00',
                'discount': '0'
            })
        ]
        
        response = self.client.post(reverse('sales:sale_create'), {
            'customer': self.customer.id,
            'sale_date': timezone.now().strftime('%Y-%m-%d'),
            'discount_amount': '0',
            'tax_amount': '0',
            'notes': '',
            'items': items_data
        })
        
        self.assertEqual(response.status_code, 302)
        
        sale = Sale.objects.first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.total_amount, Decimal('2000.00'))
        
        # Verify profit calculation
        # 2 units * (1000 - 500) = 1000 profit
        self.assertEqual(sale.total_cost, Decimal('1000.00'))
        self.assertEqual(sale.profit, Decimal('1000.00'))
        
        # Verify stock deduction
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, 18)
        
        # Verify customer balance
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_due, Decimal('2000.00'))

    def test_sale_cancellation(self):
        self.client.force_login(self.user)
        
        # Create a sale first
        sale = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.now(),
            total_amount=Decimal('1000.00'),
            total_cost=Decimal('500.00'),
            subtotal=Decimal('1000.00'),
            created_by=self.user
        )
        
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            warehouse=self.warehouse,
            quantity=1,
            unit_price=Decimal('1000.00'),
            cost_price=Decimal('500.00')
        )
        
        # Simulate previous sale effects
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        stock.quantity -= 1
        stock.save()
        self.customer.total_due += Decimal('1000.00')
        self.customer.save()
        
        # Cancel the sale
        response = self.client.post(reverse('sales:sale_cancel', args=[sale.id]))
        self.assertEqual(response.status_code, 302)
        
        sale.refresh_from_db()
        self.assertEqual(sale.status, 'cancelled')
        
        # Stock restored
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 20)
        
        # Balance restored
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_due, Decimal('0.00'))
