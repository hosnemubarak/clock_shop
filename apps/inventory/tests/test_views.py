from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth.models import User, Permission
from apps.inventory.models import Product, Category, Brand
from apps.inventory.views import product_list, product_detail


@override_settings(ENABLE_RBAC=True)
class ProductAddStockPermissionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.category = Category.objects.create(name='Test Category')
        self.brand = Brand.objects.create(name='Test Brand')
        self.product = Product.objects.create(
            sku='TEST-SKU-001',
            category=self.category,
            brand=self.brand,
            default_selling_price=100.00
        )
        
        view_perm = Permission.objects.get(codename='view_product', content_type__app_label='inventory')
        add_purchase_perm = Permission.objects.get(codename='add_purchase', content_type__app_label='inventory')

        # User with view_product permission only
        self.user_without_add_stock = User.objects.create_user(
            username='user_view_only', password='password123'
        )
        self.user_without_add_stock.user_permissions.add(view_perm)
        
        # User with view_product AND add_purchase permission
        self.user_with_add_stock = User.objects.create_user(
            username='user_with_add_stock', password='password123'
        )
        self.user_with_add_stock.user_permissions.add(view_perm, add_purchase_perm)

    def test_product_list_add_stock_button_visibility(self):
        # User WITHOUT add_purchase permission
        request = self.factory.get('/inventory/products/')
        request.user = self.user_without_add_stock
        response = product_list(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertNotIn('openQuickAddStockModal', content)
        self.assertNotIn('title="Add Stock"', content)

        # User WITH add_purchase permission
        request = self.factory.get('/inventory/products/')
        request.user = self.user_with_add_stock
        response = product_list(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('openQuickAddStockModal', content)
        self.assertIn('title="Add Stock"', content)

    def test_product_detail_add_stock_button_visibility(self):
        # User WITHOUT add_purchase permission
        request = self.factory.get(f'/inventory/products/{self.product.pk}/')
        request.user = self.user_without_add_stock
        response = product_detail(request, pk=self.product.pk)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertNotIn('openQuickAddStockModal', content)
        self.assertNotIn('Quick Stock', content)

        # User WITH add_purchase permission
        request = self.factory.get(f'/inventory/products/{self.product.pk}/')
        request.user = self.user_with_add_stock
        response = product_detail(request, pk=self.product.pk)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('openQuickAddStockModal', content)
        self.assertIn('Quick Stock', content)

    def test_product_detail_est_value_hidden_without_cost_permission(self):
        request = self.factory.get(f'/inventory/products/{self.product.pk}/')
        request.user = self.user_without_add_stock
        response = product_detail(request, pk=self.product.pk)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertNotIn('Est. Value', content)
