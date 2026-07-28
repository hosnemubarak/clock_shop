from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from django.utils import timezone
from apps.inventory.models import Category, Brand, Product, ProductStock
from apps.warehouse.models import Warehouse, StockTransfer, StockTransferItem

class WarehouseTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        
        self.source_warehouse = Warehouse.objects.create(name='Main Warehouse', code='MAIN')
        self.dest_warehouse = Warehouse.objects.create(name='Shop Warehouse', code='SHOP', is_shop=True)
        
        self.category = Category.objects.create(name='Electronics')
        self.brand = Brand.objects.create(name='TechBrand')
        
        self.product = Product.objects.create(
            sku='PHONE-X',
            category=self.category,
            brand=self.brand,
            default_selling_price=Decimal('1000.00'),
            average_cost=Decimal('500.00'),
            total_stock=20
        )
        
        # Add initial stock to source
        ProductStock.objects.create(
            product=self.product,
            warehouse=self.source_warehouse,
            quantity=20
        )

    def test_stock_transfer_workflow(self):
        transfer = StockTransfer.objects.create(
            source_warehouse=self.source_warehouse,
            destination_warehouse=self.dest_warehouse,
            transfer_date=timezone.now(),
            status='pending',
            created_by=self.user
        )
        
        StockTransferItem.objects.create(
            transfer=transfer,
            product=self.product,
            quantity=5
        )
        
        # Complete transfer
        transfer.complete_transfer()
        self.assertEqual(transfer.status, 'completed')
        
        # Check source reduced
        source_stock = ProductStock.objects.get(product=self.product, warehouse=self.source_warehouse)
        self.assertEqual(source_stock.quantity, 15)
        
        # Check dest increased
        dest_stock = ProductStock.objects.get(product=self.product, warehouse=self.dest_warehouse)
        self.assertEqual(dest_stock.quantity, 5)
        
        # Total stock unchanged
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 20)

    def test_insufficient_stock_transfer(self):
        transfer = StockTransfer.objects.create(
            source_warehouse=self.source_warehouse,
            destination_warehouse=self.dest_warehouse,
            transfer_date=timezone.now(),
            status='pending',
            created_by=self.user
        )
        
        StockTransferItem.objects.create(
            transfer=transfer,
            product=self.product,
            quantity=25 # More than available 20
        )
        
        with self.assertRaises(ValueError):
            transfer.complete_transfer()
