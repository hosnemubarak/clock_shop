from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from django.utils import timezone
from django.urls import reverse

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

    def test_sale_item_total_price_nets_line_discount(self):
        """SaleItem.total_price is quantity * unit_price - discount, and
        Sale.calculate_totals() must agree with what SaleService writes, otherwise
        recalculating a sale silently rewrites its invoice total."""
        sale = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.localdate(),
            discount_amount=Decimal('100.00'),
            created_by=self.user,
        )
        item = SaleItem.objects.create(
            sale=sale,
            product=self.product,
            warehouse=self.warehouse,
            quantity=3,
            unit_price=Decimal('1000.00'),
            cost_price=Decimal('500.00'),
            discount=Decimal('250.00'),
        )

        self.assertEqual(item.total_price, Decimal('2750.00'))
        self.assertEqual(item.total_cost, Decimal('1500.00'))

        sale.calculate_totals()
        sale.refresh_from_db()
        self.assertEqual(sale.subtotal, Decimal('2750.00'))
        self.assertEqual(sale.total_cost, Decimal('1500.00'))
        # subtotal - order discount + tax
        self.assertEqual(sale.total_amount, Decimal('2650.00'))

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
