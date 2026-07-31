from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from django.utils import timezone
from apps.inventory.models import Category, Brand, Product, Purchase, PurchaseItem, ProductStock, StockOut, StockOutItem
from apps.warehouse.models import Warehouse

class InventoryTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        
        self.warehouse = Warehouse.objects.create(name='Main Warehouse', code='MAIN')
        self.warehouse2 = Warehouse.objects.create(name='Shop Warehouse', code='SHOP', is_shop=True)
        
        self.category = Category.objects.create(name='Electronics')
        self.brand = Brand.objects.create(name='TechBrand')
        
        self.product = Product.objects.create(
            sku='PHONE-X',
            category=self.category,
            brand=self.brand,
            default_selling_price=Decimal('1000.00'),
            average_cost=Decimal('0.00')
        )

    def test_wac_calculation(self):
        # Initial purchase (0 + 10 * 500) / 10 = 500
        self.product.recalculate_average_cost(10, Decimal('500.00'))
        self.assertEqual(self.product.average_cost, Decimal('500.00'))
        # Manually update stock as would happen in view
        self.product.total_stock = 10
        self.product.save()
        
        # Second purchase (10 * 500 + 5 * 800) / 15 = 9000 / 15 = 600
        self.product.recalculate_average_cost(5, Decimal('800.00'))
        self.assertEqual(self.product.average_cost, Decimal('600.00'))
        self.product.total_stock = 15
        self.product.save()
        
        # Third purchase (15 * 600 + 5 * 200) / 20 = 10000 / 20 = 500
        self.product.recalculate_average_cost(5, Decimal('200.00'))
        self.assertEqual(self.product.average_cost, Decimal('500.00'))

    def test_update_total_stock(self):
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=5)
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse2, quantity=10)
        
        self.product.update_total_stock()
        self.assertEqual(self.product.total_stock, 15)

    def test_purchase_view(self):
        from django.urls import reverse
        self.client.force_login(self.user)
        import json
        items_data = [
            json.dumps({
                'product_id': self.product.id,
                'warehouse_id': self.warehouse.id,
                'quantity': '10',
                'unit_price': '400.00'
            })
        ]
        
        response = self.client.post(reverse('inventory:purchase_create'), {
            'supplier': 'Tech Supplier',
            'purchase_date': timezone.localdate(),
            'total_amount': '0',
            'items': items_data
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Check stock and WAC
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 10)
        self.assertEqual(self.product.average_cost, Decimal('400.00'))
        
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, 10)

    def test_stockout_workflow(self):
        # Add initial stock
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=20)
        self.product.total_stock = 20
        self.product.average_cost = Decimal('100.00')
        self.product.save()
        
        stockout = StockOut.objects.create(
            warehouse=self.warehouse,
            reason='damage',
            notes='Damaged goods',
            stockout_date=timezone.now(),
            status='pending',
            created_by=self.user
        )
        
        StockOutItem.objects.create(
            stockout=stockout,
            product=self.product,
            quantity=5
        )
        
        # Complete stock out
        stockout.complete_stockout()
        
        self.assertEqual(stockout.status, 'completed')
        
        # Check stock reduction
        stock = ProductStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, 15)
        
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 15)

    def test_insufficient_stockout(self):
        # Add initial stock
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=3)
        self.product.total_stock = 3
        self.product.save()
        
        stockout = StockOut.objects.create(
            warehouse=self.warehouse,
            reason='damage',
            stockout_date=timezone.now(),
            status='pending',
            created_by=self.user
        )
        
        StockOutItem.objects.create(
            stockout=stockout,
            product=self.product,
            quantity=5
        )
        
        # Should raise ValueError when trying to complete
        with self.assertRaises(ValueError):
            stockout.complete_stockout()
