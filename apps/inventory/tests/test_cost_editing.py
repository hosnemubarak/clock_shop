import json
from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User, Permission, Group
from django.core.management import call_command

from apps.core.models import AuditLog
from apps.inventory.models import Product, Category, Brand, ProductStock, Purchase, PurchaseItem, StockOut, StockOutItem
from apps.inventory.services import (recalculate_product_costing, update_purchase_item_cost,
                                    update_purchase_and_costs, get_product_stock_history)
from apps.sales.models import Sale, SaleItem
from apps.warehouse.models import Warehouse
from apps.customers.models import Customer


class CostPriceEditingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_user', password='password123', is_superuser=True)
        self.client.force_login(self.user)

        self.warehouse = Warehouse.objects.create(name='Main Shop', code='SHOP', is_shop=True)
        self.category = Category.objects.create(name='Watches')
        self.brand = Brand.objects.create(name='Seiko')

        self.product = Product.objects.create(
            sku='SEIKO-PRO-01',
            category=self.category,
            brand=self.brand,
            default_selling_price=Decimal('1000.00'),
            average_cost=Decimal('0.00'),
            total_stock=0
        )

    def test_update_purchase_item_cost_single_purchase(self):
        """Editing cost price on a single purchase item updates item, purchase total, and product average cost."""
        purchase = Purchase.objects.create(
            supplier='Official Seiko Supplier',
            purchase_date=timezone.localdate(),
            total_amount=Decimal('5000.00'),
            created_by=self.user
        )
        item = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            warehouse=self.warehouse,
            quantity=10,
            unit_price=Decimal('500.00')
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=10)
        self.product.update_total_stock()
        self.product.average_cost = Decimal('500.00')
        self.product.save(update_fields=['average_cost'])

        # Edit unit price from 500 to 400
        result = update_purchase_item_cost(
            purchase_item=item,
            new_unit_price=Decimal('400.00'),
            user=self.user,
            reason='Correcting typo on invoice'
        )

        item.refresh_from_db()
        purchase.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(item.unit_price, Decimal('400.00'))
        self.assertEqual(item.total_price, Decimal('4000.00'))
        self.assertEqual(purchase.total_amount, Decimal('4000.00'))
        self.assertEqual(self.product.average_cost, Decimal('400.00'))
        self.assertEqual(self.product.total_stock, 10)  # Quantity unchanged!

        # Check AuditLog
        log = AuditLog.objects.filter(model_name='Purchase', object_id=purchase.id).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes['old_unit_price'], '500.00')
        self.assertEqual(log.changes['new_unit_price'], '400.00')
        self.assertEqual(log.changes['old_purchase_total'], '5000.00')
        self.assertEqual(log.changes['new_purchase_total'], '4000.00')
        self.assertEqual(log.changes['reason'], 'Correcting typo on invoice')

    def test_weighted_average_cost_recalculated_across_multiple_purchases(self):
        """Editing an earlier purchase cost accurately updates moving weighted average cost."""
        today = timezone.localdate()
        yesterday = today - timezone.timedelta(days=1)

        # PO 1: 10 units @ 100.00
        po1 = Purchase.objects.create(
            supplier='Supplier A', purchase_date=yesterday,
            total_amount=Decimal('1000.00'), created_by=self.user
        )
        po1_item = PurchaseItem.objects.create(
            purchase=po1, product=self.product, warehouse=self.warehouse,
            quantity=10, unit_price=Decimal('100.00')
        )

        # PO 2: 10 units @ 200.00
        po2 = Purchase.objects.create(
            supplier='Supplier B', purchase_date=today,
            total_amount=Decimal('2000.00'), created_by=self.user
        )
        po2_item = PurchaseItem.objects.create(
            purchase=po2, product=self.product, warehouse=self.warehouse,
            quantity=10, unit_price=Decimal('200.00')
        )

        stock = ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=20)
        self.product.update_total_stock()
        # Initial WAC = (10*100 + 10*200) / 20 = 150.00
        recalculate_product_costing(self.product)
        self.product.refresh_from_db()
        self.assertEqual(self.product.average_cost, Decimal('150.00'))

        # Now edit PO 1 price to 160.00
        update_purchase_item_cost(
            purchase_item=po1_item,
            new_unit_price=Decimal('160.00'),
            user=self.user
        )

        self.product.refresh_from_db()
        # New WAC = (10*160 + 10*200) / 20 = 3600 / 20 = 180.00
        self.assertEqual(self.product.average_cost, Decimal('180.00'))

        # Verify inventory stock valuation
        self.assertEqual(stock.total_value, Decimal('20') * Decimal('180.00'))
        self.assertEqual(self.warehouse.get_total_stock_value(), Decimal('3600.00'))

    def test_historical_sale_cogs_and_profit_reports_updated(self):
        """Historical sales that occurred after the purchase have their COGS updated and profit corrected."""
        today = timezone.localdate()
        day1 = today - timezone.timedelta(days=2)
        day2 = today - timezone.timedelta(days=1)

        # Purchase on Day 1: 10 units @ 100.00
        po = Purchase.objects.create(
            supplier='Supplier A', purchase_date=day1,
            total_amount=Decimal('1000.00'), created_by=self.user
        )
        po_item = PurchaseItem.objects.create(
            purchase=po, product=self.product, warehouse=self.warehouse,
            quantity=10, unit_price=Decimal('100.00')
        )
        stock = ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=10)
        self.product.update_total_stock()
        recalculate_product_costing(self.product)

        # Sale on Day 2: 4 units sold @ 300.00 each
        sale = Sale.objects.create(
            sale_date=day2,
            subtotal=Decimal('1200.00'),
            total_amount=Decimal('1200.00'),
            total_cost=Decimal('400.00'),
            status=Sale.Status.COMPLETED
        )
        sale_item = SaleItem.objects.create(
            sale=sale,
            product=self.product,
            warehouse=self.warehouse,
            quantity=4,
            unit_price=Decimal('300.00'),
            cost_price=Decimal('100.00')
        )
        stock.quantity = 6
        stock.save()
        self.product.update_total_stock()

        self.assertEqual(sale.total_cost, Decimal('400.00'))
        self.assertEqual(sale.profit, Decimal('800.00'))

        # Now suppose PO cost was entered incorrectly as 100, but was actually 150
        update_purchase_item_cost(
            purchase_item=po_item,
            new_unit_price=Decimal('150.00'),
            user=self.user
        )

        sale_item.refresh_from_db()
        sale.refresh_from_db()
        self.product.refresh_from_db()

        # Sale item cost price should now be 150.00
        self.assertEqual(sale_item.cost_price, Decimal('150.00'))
        # Sale total cost should be 4 * 150.00 = 600.00
        self.assertEqual(sale.total_cost, Decimal('600.00'))
        # Sale profit should be 1200 - 600 = 600.00 (was 800.00)
        self.assertEqual(sale.profit, Decimal('600.00'))
        # Customer sale total amount (invoice amount) must be preserved!
        self.assertEqual(sale.total_amount, Decimal('1200.00'))
        self.assertEqual(sale.subtotal, Decimal('1200.00'))

        # Remaining stock valuation: 6 units @ 150 = 900.00
        self.assertEqual(self.product.average_cost, Decimal('150.00'))
        self.assertEqual(stock.total_value, Decimal('900.00'))

    def test_stockout_item_cost_updated(self):
        """StockOut items that recorded cost price at previous average cost are updated."""
        today = timezone.now()
        po = Purchase.objects.create(
            supplier='Supplier A', purchase_date=today.date(),
            total_amount=Decimal('1000.00'), created_by=self.user
        )
        po_item = PurchaseItem.objects.create(
            purchase=po, product=self.product, warehouse=self.warehouse,
            quantity=10, unit_price=Decimal('100.00')
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=10)
        self.product.update_total_stock()
        recalculate_product_costing(self.product)

        stockout = StockOut.objects.create(
            warehouse=self.warehouse,
            reason=StockOut.Reason.DAMAGE,
            status=StockOut.Status.COMPLETED,
            stockout_date=today,
            total_value=Decimal('200.00'),
            created_by=self.user
        )
        so_item = StockOutItem.objects.create(
            stockout=stockout,
            product=self.product,
            quantity=2,
            cost_price=Decimal('100.00')
        )

        # Update PO cost to 140.00
        update_purchase_item_cost(po_item, Decimal('140.00'), user=self.user)

        so_item.refresh_from_db()
        stockout.refresh_from_db()
        self.assertEqual(so_item.cost_price, Decimal('140.00'))
        self.assertEqual(stockout.total_value, Decimal('280.00'))

    def test_purchase_edit_view(self):
        """GET and POST on purchase_edit view updates purchase header and item prices."""
        purchase = Purchase.objects.create(
            supplier='Old Supplier',
            purchase_date=timezone.localdate(),
            total_amount=Decimal('2000.00'),
            created_by=self.user
        )
        item1 = PurchaseItem.objects.create(
            purchase=purchase, product=self.product, warehouse=self.warehouse,
            quantity=4, unit_price=Decimal('500.00')
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=4)
        self.product.update_total_stock()
        recalculate_product_costing(self.product)

        # GET
        url = reverse('inventory:purchase_edit', args=[purchase.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'SEIKO-PRO-01')

        # POST
        post_data = {
            'supplier': 'New Verified Supplier',
            'purchase_date': timezone.localdate().strftime('%Y-%m-%d'),
            'notes': 'Updated delivery invoice notes',
            'reason': 'Supplier price revision',
            f'item_price_{item1.id}': '450.00',
        }
        post_resp = self.client.post(url, post_data)
        self.assertEqual(post_resp.status_code, 302)
        self.assertRedirects(post_resp, reverse('inventory:purchase_detail', args=[purchase.pk]))

        purchase.refresh_from_db()
        item1.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(purchase.supplier, 'New Verified Supplier')
        self.assertEqual(item1.unit_price, Decimal('450.00'))
        self.assertEqual(purchase.total_amount, Decimal('1800.00'))
        self.assertEqual(self.product.average_cost, Decimal('450.00'))

    def test_api_edit_purchase_item_cost(self):
        """AJAX API endpoint updates cost and returns JSON."""
        purchase = Purchase.objects.create(
            supplier='API Supplier',
            purchase_date=timezone.localdate(),
            total_amount=Decimal('1000.00'),
            created_by=self.user
        )
        item = PurchaseItem.objects.create(
            purchase=purchase, product=self.product, warehouse=self.warehouse,
            quantity=5, unit_price=Decimal('200.00')
        )
        ProductStock.objects.create(product=self.product, warehouse=self.warehouse, quantity=5)
        self.product.update_total_stock()
        recalculate_product_costing(self.product)

        url = reverse('inventory:api_edit_purchase_item_cost', args=[item.pk])
        resp = self.client.post(
            url,
            data=json.dumps({'unit_price': '220.00', 'reason': 'Correcting input mistake'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['new_unit_price'], '220.00')
        self.assertEqual(data['new_purchase_total'], '1100.00')
        self.assertEqual(data['new_average_cost'], '220.00')

        item.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal('220.00'))

    def test_validation_rejects_negative_price(self):
        """Negative unit price is rejected both via API and via form."""
        purchase = Purchase.objects.create(
            supplier='Test Supplier', purchase_date=timezone.localdate(),
            total_amount=Decimal('100.00'), created_by=self.user
        )
        item = PurchaseItem.objects.create(
            purchase=purchase, product=self.product, warehouse=self.warehouse,
            quantity=1, unit_price=Decimal('100.00')
        )

        url = reverse('inventory:api_edit_purchase_item_cost', args=[item.pk])
        resp = self.client.post(
            url,
            data=json.dumps({'unit_price': '-50.00'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        self.assertIn('negative', resp.json()['error'])

        # Service level rejection
        with self.assertRaises(ValueError):
            update_purchase_item_cost(item, Decimal('-10.00'))

    @override_settings(ENABLE_RBAC=True)
    def test_permission_checks_enforce_authorization(self):
        """Users without inventory.change_purchase are denied access."""
        call_command('setup_groups', verbosity=0)

        # Cashier user
        cashier = User.objects.create_user(username='cashier_test', password='password123')
        cashier.groups.add(Group.objects.get(name='Cashier'))

        # Manager user
        manager = User.objects.create_user(username='manager_test', password='password123')
        manager.groups.add(Group.objects.get(name='Manager'))

        purchase = Purchase.objects.create(
            supplier='Supplier X', purchase_date=timezone.localdate(),
            total_amount=Decimal('100.00'), created_by=self.user
        )
        item = PurchaseItem.objects.create(
            purchase=purchase, product=self.product, warehouse=self.warehouse,
            quantity=1, unit_price=Decimal('100.00')
        )

        edit_url = reverse('inventory:purchase_edit', args=[purchase.pk])
        api_url = reverse('inventory:api_edit_purchase_item_cost', args=[item.pk])

        # 1. Cashier attempts edit: denied
        self.client.force_login(cashier)
        resp = self.client.get(edit_url)
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('core:unauthorized'))

        ajax_resp = self.client.post(
            api_url,
            data=json.dumps({'unit_price': '150.00'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(ajax_resp.status_code, 403)

        # 2. Manager attempts edit: allowed
        self.client.force_login(manager)
        resp = self.client.get(edit_url)
        self.assertEqual(resp.status_code, 200)

        ajax_resp = self.client.post(
            api_url,
            data=json.dumps({'unit_price': '150.00'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(ajax_resp.status_code, 200)
        self.assertTrue(ajax_resp.json()['success'])

    def test_stock_history_includes_purchase_id_for_navigation(self):
        """get_product_stock_history includes purchase_id so UI can link to purchase details."""
        purchase = Purchase.objects.create(
            supplier='Nav Supplier', purchase_date=timezone.localdate(),
            total_amount=Decimal('100.00'), created_by=self.user
        )
        item = PurchaseItem.objects.create(
            purchase=purchase, product=self.product, warehouse=self.warehouse,
            quantity=2, unit_price=Decimal('50.00')
        )

        history = get_product_stock_history(self.product)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['type'], 'STOCK_IN')
        self.assertEqual(history[0]['purchase_id'], purchase.id)
        self.assertEqual(history[0]['item_id'], item.id)
