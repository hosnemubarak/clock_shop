from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from decimal import Decimal
from django.utils import timezone
from django.urls import reverse
from datetime import date

from apps.inventory.models import Category, Brand, Product, ProductStock
from apps.warehouse.models import Warehouse
from apps.sales.models import Sale

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
        response = self.client.get(reverse('reports:stock_report'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('stock_summary', response.context)
        self.assertEqual(response.context['totals']['total_value'], Decimal('10000.00'))
        self.assertEqual(response.context['totals']['total_items'], 20)

    def test_dead_stock_report_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('reports:dead_stock_report'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('dead_stock', response.context)
        
    def test_low_stock_report_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('reports:stock_report'), {'stock_filter': 'low'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('stock_summary', response.context)

    @override_settings(TIME_ZONE='Asia/Dhaka', USE_TZ=True)
    def test_sales_report_groupings_with_non_utc_timezone(self):
        """Sale.sale_date is a DateField. Grouping it with TruncDate made Django's
        SQLite UDF call timezone.localtime() on a date, which has no utcoffset(),
        surfacing as 'OperationalError: user-defined function raised exception'.
        It only triggered once TIME_ZONE differed from UTC, so pin the timezone here.
        """
        self.client.force_login(self.user)
        sale = Sale.objects.create(
            sale_date=timezone.localdate(),
            status=Sale.Status.COMPLETED,
            subtotal=Decimal('1000.00'),
            total_amount=Decimal('1000.00'),
            total_cost=Decimal('500.00'),
            created_by=self.user,
        )

        for group_by in ('day', 'week', 'month'):
            with self.subTest(group_by=group_by):
                response = self.client.get(
                    reverse('reports:sales_report'), {'group_by': group_by}
                )
                self.assertEqual(response.status_code, 200)
                rows = list(response.context['sales_by_period'])
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['total'], sale.total_amount)
                self.assertEqual(rows[0]['count'], 1)
                # Each grouping must yield a real date, not a raw string.
                self.assertIsInstance(rows[0]['period'], date)
