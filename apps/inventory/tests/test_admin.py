from decimal import Decimal
from django.test import TestCase
from apps.inventory.models import Category, Brand, Product
from apps.inventory.admin import CategoryResource, BrandResource, ProductResource
from tablib import Dataset


class AdminImportExportTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Test Category', description='Cat desc')
        self.brand = Brand.objects.create(name='Test Brand', description='Brand desc')
        self.product = Product.objects.create(
            sku='TEST-SKU-100',
            category=self.category,
            brand=self.brand,
            default_selling_price=Decimal('500.00'),
            total_stock=10,
            average_cost=Decimal('300.00'),
        )

    def test_category_export(self):
        resource = CategoryResource()
        dataset = resource.export(Category.objects.all())
        self.assertIn('Test Category', str(dataset.csv))

    def test_brand_export(self):
        resource = BrandResource()
        dataset = resource.export(Brand.objects.all())
        self.assertIn('Test Brand', str(dataset.csv))

    def test_product_export(self):
        resource = ProductResource()
        dataset = resource.export(Product.objects.all())
        self.assertIn('TEST-SKU-100', str(dataset.csv))
        self.assertIn('Test Category', str(dataset.csv))
        self.assertIn('Test Brand', str(dataset.csv))

    def test_category_import_create_and_update(self):
        resource = CategoryResource()
        dataset = Dataset()
        dataset.headers = ['id', 'name', 'description', 'is_active', 'created_at', 'updated_at']
        # 1. Create new category with empty id and empty timestamps
        dataset.append(['', 'New Imported Category', 'Imported desc', '1', '', ''])
        # 2. Update existing category by name with empty id and empty timestamps
        dataset.append(['', 'Test Category', 'Updated cat desc', '1', '', ''])
        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        self.assertTrue(Category.objects.filter(name='New Imported Category').exists())
        self.category.refresh_from_db()
        self.assertEqual(self.category.description, 'Updated cat desc')

    def test_brand_import_create_and_update(self):
        resource = BrandResource()
        dataset = Dataset()
        dataset.headers = ['id', 'name', 'description', 'is_active', 'created_at', 'updated_at']
        # 1. Create new brand
        dataset.append(['', 'New Imported Brand', 'Imported desc', '1', '', ''])
        # 2. Update existing brand by name with empty id
        dataset.append(['', 'Test Brand', 'Updated brand desc', '1', '', ''])
        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        self.assertTrue(Brand.objects.filter(name='New Imported Brand').exists())
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.description, 'Updated brand desc')

    def test_product_import_new_by_sku(self):
        resource = ProductResource()
        dataset = Dataset()
        dataset.headers = ['id', 'sku', 'brand', 'category', 'description', 'default_selling_price', 'total_stock', 'average_cost', 'is_active', 'created_at', 'updated_at']
        dataset.append(['', 'NEW-SKU-200', 'Test Brand', 'Test Category', 'Sample Product', '750.00', '0', '0.00', '1', '', ''])
        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        self.assertTrue(Product.objects.filter(sku='NEW-SKU-200').exists())

    def test_product_update_by_sku_with_empty_id(self):
        resource = ProductResource()
        dataset = Dataset()
        dataset.headers = ['id', 'sku', 'brand', 'category', 'description', 'default_selling_price', 'total_stock', 'average_cost', 'is_active', 'created_at', 'updated_at']
        # Updating TEST-SKU-100 with empty id must NOT crash with UNIQUE constraint
        dataset.append(['', 'TEST-SKU-100', 'Test Brand', 'Test Category', 'Updated Description', '550.00', '', '', '1', '', ''])
        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        self.product.refresh_from_db()
        self.assertEqual(self.product.description, 'Updated Description')
        self.assertEqual(self.product.default_selling_price, Decimal('550.00'))

    def test_product_computed_fields_protected_from_tampering(self):
        resource = ProductResource()
        dataset = Dataset()
        dataset.headers = ['id', 'sku', 'brand', 'category', 'description', 'default_selling_price', 'total_stock', 'average_cost', 'is_active']
        # Try to tamper total_stock and average_cost
        dataset.append(['', 'TEST-SKU-100', 'Test Brand', 'Test Category', 'Desc', '500.00', '9999', '1.00', '1'])
        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        self.product.refresh_from_db()
        # Computed fields must remain protected
        self.assertEqual(self.product.total_stock, 10)
        self.assertEqual(self.product.average_cost, Decimal('300.00'))

    def test_product_export_reimport_roundtrip(self):
        resource = ProductResource()
        export_dataset = resource.export(Product.objects.filter(sku='TEST-SKU-100'))
        
        # Modify price on exported data and re-import
        dataset = Dataset(*export_dataset)
        dataset.headers = export_dataset.headers
        row = list(dataset[0])
        price_idx = dataset.headers.index('default_selling_price')
        row[price_idx] = '620.00'
        dataset[0] = row

        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        self.product.refresh_from_db()
        self.assertEqual(self.product.default_selling_price, Decimal('620.00'))

    def test_product_import_nonexistent_foreign_key_has_errors(self):
        resource = ProductResource()
        dataset = Dataset()
        dataset.headers = ['sku', 'brand', 'category', 'default_selling_price']
        dataset.append(['FAIL-SKU', 'NonExistentBrand', 'Test Category', '100.00'])
        result = resource.import_data(dataset, dry_run=False)
        self.assertTrue(result.has_errors())
