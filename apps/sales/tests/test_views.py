"""Tests for the sale screen: the product-search endpoint and every checkout path.

`sale_create` renders the page and nothing else -- the page posts JSON to
`sales:pos_checkout`, so that is where the write coverage lives.
"""

import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.customers.models import Customer, Payment
from apps.inventory.models import Brand, Category, Product, ProductStock
from apps.sales.models import Sale, SaleItem
from apps.warehouse.models import Warehouse


class SaleScreenTestMixin:
    def setUp(self):
        self.user = User.objects.create_user(username='cashier', password='password')
        self.shop = Warehouse.objects.create(name='Main Shop', code='SHOP', is_shop=True)
        self.depot = Warehouse.objects.create(name='Back Depot', code='DEPOT', is_shop=False)

        self.watches = Category.objects.create(name='Wrist Watches')
        self.clocks = Category.objects.create(name='Wall Clocks')
        self.seiko = Brand.objects.create(name='Seiko')
        self.casio = Brand.objects.create(name='Casio')

        self.product = Product.objects.create(
            sku='SEIKO-5',
            category=self.watches,
            brand=self.seiko,
            default_selling_price=Decimal('1000.00'),
            average_cost=Decimal('600.00'),
            total_stock=10,
        )
        ProductStock.objects.create(product=self.product, warehouse=self.shop, quantity=10)

        self.second = Product.objects.create(
            sku='CASIO-W1',
            category=self.clocks,
            brand=self.casio,
            default_selling_price=Decimal('500.00'),
            average_cost=Decimal('250.00'),
            total_stock=4,
        )
        ProductStock.objects.create(product=self.second, warehouse=self.shop, quantity=4)

        # Stocked in the depot only: not sellable from the shop till.
        self.depot_only = Product.objects.create(
            sku='DEPOT-ONLY',
            category=self.clocks,
            brand=self.casio,
            default_selling_price=Decimal('300.00'),
            average_cost=Decimal('150.00'),
            total_stock=7,
        )
        ProductStock.objects.create(product=self.depot_only, warehouse=self.depot, quantity=7)

        self.customer = Customer.objects.create(
            name='Rahim Uddin', 
            phone='01700000000',
            credit_limit=Decimal('5000.00')
        )

        self.client.force_login(self.user)

    def checkout(self, payload):
        return self.client.post(
            reverse('sales:pos_checkout'),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def cart(self, **overrides):
        payload = {
            'items': [{
                'product_id': self.product.id,
                'quantity': 2,
                'unit_price': '1000.00',
            }],
            'payment_amount': '2000.00',
            'payment_method': 'cash',
        }
        payload.update(overrides)
        return payload

    def assertNoWriteHappened(self, expected_shop_qty=10):
        """A rejected checkout must leave no Sale row and no stock drift."""
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(SaleItem.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        stock = ProductStock.objects.get(product=self.product, warehouse=self.shop)
        self.assertEqual(stock.quantity, expected_shop_qty)


class ProductSearchApiTests(SaleScreenTestMixin, TestCase):
    def search(self, **params):
        return self.client.get(reverse('sales:api_product_search'), params)

    def test_requires_login(self):
        self.client.logout()
        response = self.search(q='SEIKO')
        self.assertEqual(response.status_code, 302)

    def test_blank_query_returns_bounded_catalogue(self):
        response = self.search()
        self.assertEqual(response.status_code, 200)
        skus = [row['sku'] for row in response.json()['results']]
        self.assertCountEqual(skus, ['SEIKO-5', 'CASIO-W1', 'DEPOT-ONLY'])

    def test_matches_sku_brand_and_category(self):
        for query, expected in (
            ('seiko-5', 'SEIKO-5'),      # SKU, case-insensitive
            ('Casio', 'CASIO-W1'),        # brand name
            ('Wrist', 'SEIKO-5'),         # category name
        ):
            with self.subTest(query=query):
                results = self.search(q=query).json()['results']
                self.assertIn(expected, [row['sku'] for row in results])

    def test_exact_sku_match_sorts_first(self):
        """A barcode scan is an exact SKU: it must be the row Enter would add."""
        Product.objects.create(
            sku='SEIKO-50',
            category=self.watches,
            brand=self.seiko,
            default_selling_price=Decimal('900.00'),
            average_cost=Decimal('500.00'),
            total_stock=99,
        )
        results = self.search(q='SEIKO-5').json()['results']
        self.assertEqual(results[0]['sku'], 'SEIKO-5')

    def test_reports_shop_stock_separately_from_total(self):
        row = next(r for r in self.search(q='DEPOT-ONLY').json()['results'])
        self.assertEqual(row['shop_stock'], 0)
        self.assertEqual(row['total_stock'], 7)

    def test_limit_is_validated_and_capped(self):
        self.assertEqual(len(self.search(q='', limit=1).json()['results']), 1)
        self.assertTrue(self.search(q='', limit=1).json()['truncated'])
        # Garbage and oversized limits fall back / clamp instead of erroring.
        self.assertEqual(self.search(q='', limit='abc').status_code, 200)
        self.assertEqual(self.search(q='', limit=9999).status_code, 200)

    def test_query_is_treated_as_a_literal(self):
        for query in ("'; DROP TABLE inventory_product; --", '%', '_'):
            with self.subTest(query=query):
                response = self.search(q=query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['results'], [])

    def test_query_count_is_constant(self):
        """Search must not go N+1 as the result set grows."""
        with self.assertNumQueries(4):
            self.search(q='')


class PosCheckoutTests(SaleScreenTestMixin, TestCase):
    def test_walk_in_cash_sale(self):
        response = self.checkout(self.cart())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

        sale = Sale.objects.get(pk=response.json()['sale_id'])
        self.assertIsNone(sale.customer)
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertEqual(sale.subtotal, Decimal('2000.00'))
        self.assertEqual(sale.total_amount, Decimal('2000.00'))
        self.assertEqual(sale.total_cost, Decimal('1200.00'))
        self.assertEqual(sale.paid_amount, Decimal('2000.00'))
        self.assertEqual(sale.payment_status, 'paid')

        stock = ProductStock.objects.get(product=self.product, warehouse=self.shop)
        self.assertEqual(stock.quantity, 8)
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 8)

    def test_sale_with_customer_updates_balance(self):
        response = self.checkout(self.cart(customer_id=self.customer.id))
        self.assertEqual(response.status_code, 200)

        sale = Sale.objects.get(pk=response.json()['sale_id'])
        self.assertEqual(sale.customer, self.customer)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_due, Decimal('0.00'))

    def test_multi_item_sale(self):
        response = self.checkout(self.cart(
            items=[
                {'product_id': self.product.id, 'quantity': 1, 'unit_price': '1000.00'},
                {'product_id': self.second.id, 'quantity': 3, 'unit_price': '500.00'},
            ],
            payment_amount='2500.00',
        ))
        self.assertEqual(response.status_code, 200)

        sale = Sale.objects.get(pk=response.json()['sale_id'])
        self.assertEqual(sale.items.count(), 2)
        self.assertEqual(sale.subtotal, Decimal('2500.00'))
        self.assertEqual(sale.total_cost, Decimal('1350.00'))
        self.assertEqual(
            ProductStock.objects.get(product=self.product, warehouse=self.shop).quantity, 9
        )
        self.assertEqual(
            ProductStock.objects.get(product=self.second, warehouse=self.shop).quantity, 1
        )

    def test_per_line_discount_is_persisted_and_nets_out_of_subtotal(self):
        response = self.checkout(self.cart(
            items=[{
                'product_id': self.product.id,
                'quantity': 2,
                'unit_price': '1000.00',
                'discount': '150.00',
            }],
            payment_amount='1850.00',
        ))
        self.assertEqual(response.status_code, 200)

        sale = Sale.objects.get(pk=response.json()['sale_id'])
        item = sale.items.get()
        self.assertEqual(item.discount, Decimal('150.00'))
        self.assertEqual(item.total_price, Decimal('1850.00'))
        self.assertEqual(sale.subtotal, Decimal('1850.00'))
        self.assertEqual(sale.total_amount, Decimal('1850.00'))

        # A later recalculation must not move the total.
        sale.calculate_totals()
        sale.refresh_from_db()
        self.assertEqual(sale.total_amount, Decimal('1850.00'))

    def test_order_discount_applies_on_top_of_line_discounts(self):
        response = self.checkout(self.cart(
            items=[{
                'product_id': self.product.id,
                'quantity': 2,
                'unit_price': '1000.00',
                'discount': '100.00',
            }],
            discount_amount='400.00',
            payment_amount='1500.00',
        ))
        self.assertEqual(response.status_code, 200)

        sale = Sale.objects.get(pk=response.json()['sale_id'])
        self.assertEqual(sale.subtotal, Decimal('1900.00'))
        self.assertEqual(sale.discount_amount, Decimal('400.00'))
        self.assertEqual(sale.total_amount, Decimal('1500.00'))
        self.assertEqual(sale.payment_status, 'paid')

    def test_credit_sale_with_no_payment(self):
        response = self.checkout(self.cart(
            customer_id=self.customer.id, payment_amount='0'
        ))
        self.assertEqual(response.status_code, 200)

        sale = Sale.objects.get(pk=response.json()['sale_id'])
        self.assertEqual(sale.paid_amount, Decimal('0.00'))
        self.assertEqual(sale.payment_status, 'unpaid')
        self.assertEqual(Payment.objects.filter(sale=sale).count(), 0)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_due, Decimal('2000.00'))

    def test_partial_payment(self):
        response = self.checkout(self.cart(
            customer_id=self.customer.id, payment_amount='750.00'
        ))
        self.assertEqual(response.status_code, 200)

        sale = Sale.objects.get(pk=response.json()['sale_id'])
        self.assertEqual(sale.paid_amount, Decimal('750.00'))
        self.assertEqual(sale.payment_status, 'partial')
        self.assertEqual(sale.due_amount, Decimal('1250.00'))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_due, Decimal('1250.00'))

    def test_every_payment_method_is_accepted(self):
        for method in Payment.PaymentMethod.values:
            with self.subTest(method=method):
                response = self.checkout(self.cart(
                    items=[{
                        'product_id': self.product.id, 'quantity': 1, 'unit_price': '10.00',
                    }],
                    payment_amount='10.00',
                    payment_method=method,
                ))
                self.assertEqual(response.status_code, 200)
                sale_id = response.json()['sale_id']
                self.assertEqual(
                    Payment.objects.get(sale_id=sale_id).payment_method, method
                )

    def test_unknown_payment_method_is_rejected(self):
        # 'mobile_money' was in both checkout templates but is not a model choice.
        response = self.checkout(self.cart(payment_method='mobile_money'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('payment method', response.json()['message'])
        self.assertNoWriteHappened()

    def test_over_sell_is_rejected_with_no_partial_write(self):
        response = self.checkout(self.cart(
            items=[{'product_id': self.product.id, 'quantity': 11, 'unit_price': '1000.00'}]
        ))
        self.assertEqual(response.status_code, 400)
        self.assertIn('Insufficient stock', response.json()['message'])
        self.assertNoWriteHappened()

    def test_product_with_no_shop_stock_is_rejected(self):
        response = self.checkout(self.cart(
            items=[{'product_id': self.depot_only.id, 'quantity': 1, 'unit_price': '300.00'}]
        ))
        self.assertEqual(response.status_code, 400)
        self.assertIn('Insufficient stock', response.json()['message'])
        self.assertNoWriteHappened()

    def test_second_line_failure_rolls_back_the_first(self):
        response = self.checkout(self.cart(
            items=[
                {'product_id': self.product.id, 'quantity': 1, 'unit_price': '1000.00'},
                {'product_id': self.second.id, 'quantity': 99, 'unit_price': '500.00'},
            ]
        ))
        self.assertEqual(response.status_code, 400)
        self.assertNoWriteHappened()
        self.assertEqual(
            ProductStock.objects.get(product=self.second, warehouse=self.shop).quantity, 4
        )

    def test_bad_payloads_return_400(self):
        cases = {
            'empty cart': ({'items': []}, 'Cart is empty'),
            'missing product': ({'items': [{'quantity': 1, 'unit_price': '1'}]}, 'missing a product'),
            'missing price': ({'items': [{'product_id': self.product.id, 'quantity': 1}]}, 'missing a unit price'),
            'zero quantity': (self.cart(items=[{'product_id': self.product.id, 'quantity': 0, 'unit_price': '1'}]), 'greater than zero'),
            'non-numeric quantity': (self.cart(items=[{'product_id': self.product.id, 'quantity': 'two', 'unit_price': '1'}]), 'Invalid quantity'),
            'malformed price': (self.cart(items=[{'product_id': self.product.id, 'quantity': 1, 'unit_price': '12.3.4'}]), 'Invalid unit price'),
            'negative price': (self.cart(items=[{'product_id': self.product.id, 'quantity': 1, 'unit_price': '-5'}]), 'cannot be negative'),
            'unknown product': (self.cart(items=[{'product_id': 999999, 'quantity': 1, 'unit_price': '1'}]), 'not found'),
            'item not an object': ({'items': ['nope']}, 'Invalid cart item'),
        }
        for label, (payload, fragment) in cases.items():
            with self.subTest(case=label):
                response = self.checkout(payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(fragment, response.json()['message'])
                self.assertNoWriteHappened()

    def test_bad_discounts_return_400(self):
        cases = {
            'negative line discount': (
                self.cart(items=[{
                    'product_id': self.product.id, 'quantity': 1,
                    'unit_price': '100.00', 'discount': '-1',
                }]),
                'cannot be negative',
            ),
            'line discount over line total': (
                self.cart(items=[{
                    'product_id': self.product.id, 'quantity': 1,
                    'unit_price': '100.00', 'discount': '150.00',
                }]),
                'cannot exceed the line total',
            ),
            'malformed line discount': (
                self.cart(items=[{
                    'product_id': self.product.id, 'quantity': 1,
                    'unit_price': '100.00', 'discount': 'free',
                }]),
                'Invalid discount',
            ),
            'negative order discount': (self.cart(discount_amount='-50'), 'cannot be negative'),
            'order discount over subtotal': (
                self.cart(discount_amount='5000.00'), 'cannot exceed the sale subtotal'
            ),
            'negative payment': (self.cart(payment_amount='-10'), 'cannot be negative'),
        }
        for label, (payload, fragment) in cases.items():
            with self.subTest(case=label):
                response = self.checkout(payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(fragment, response.json()['message'])
                self.assertNoWriteHappened()

    def test_blank_line_discount_is_treated_as_zero(self):
        """An older client that omits or blanks the field must keep working."""
        for value in (None, '', '0'):
            with self.subTest(discount=value):
                item = {'product_id': self.product.id, 'quantity': 1, 'unit_price': '100.00'}
                if value is not None:
                    item['discount'] = value
                response = self.checkout(self.cart(items=[item], payment_amount='100.00'))
                self.assertEqual(response.status_code, 200)
                sale = Sale.objects.get(pk=response.json()['sale_id'])
                self.assertEqual(sale.items.get().discount, Decimal('0.00'))



    def test_response_carries_the_invoice_number(self):
        """The success modal shows this; without it the cashier only saw a pk."""
        response = self.checkout(self.cart())
        self.assertEqual(response.status_code, 200)

        body = response.json()
        sale = Sale.objects.get(pk=body['sale_id'])
        self.assertEqual(body['invoice_number'], sale.invoice_number)
        self.assertTrue(body['invoice_number'])

    def test_malformed_json_returns_400(self):
        response = self.client.post(
            reverse('sales:pos_checkout'), data='{not json', content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid JSON', response.json()['message'])
        self.assertNoWriteHappened()

    def test_get_is_rejected(self):
        response = self.client.get(reverse('sales:pos_checkout'))
        self.assertEqual(response.status_code, 405)

    def test_requires_login(self):
        self.client.logout()
        response = self.checkout(self.cart())
        self.assertEqual(response.status_code, 302)
        self.assertNoWriteHappened()


class SaleCreatePageTests(SaleScreenTestMixin, TestCase):
    def test_page_renders(self):
        response = self.client.get(reverse('sales:sale_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sales/sale_form.html')

    def test_payment_methods_come_from_the_model(self):
        """The template used to hardcode a 'mobile_money' option that is not a valid
        choice, so it persisted and then rendered blank on the payment reports."""
        response = self.client.get(reverse('sales:sale_create'))
        self.assertEqual(response.context['payment_methods'], Payment.PaymentMethod.choices)

    def test_page_does_not_embed_the_catalogue(self):
        """Every product and customer used to be rendered as <option> tags."""
        response = self.client.get(reverse('sales:sale_create'))
        self.assertNotIn('products', response.context)
        self.assertNotIn('customers', response.context)

    def test_customer_field_is_a_plain_hidden_input(self):
        """The customer selector no longer uses TomSelect: it is a hidden
        `customer` field driven by the page's own search dropdown, so the
        checkout POST still carries `customer_id` from an id the JS controls."""
        response = self.client.get(reverse('sales:sale_create'))
        html = response.content.decode()
        self.assertIn('id="customerId"', html)
        self.assertIn('name="customer"', html)
        self.assertIn('id="customerSearch"', html)
        # The TomSelect init keyed off a <select name="customer">; it must be gone.
        self.assertNotIn('<select name="customer"', html)
        self.assertNotIn('TomSelect', html)

    def test_page_never_writes_on_post(self):
        """The removed POST branch was a second, unreachable sale-creation path.
        Posting the form must not create anything now."""
        response = self.client.post(reverse('sales:sale_create'), {})
        self.assertIn(response.status_code, (200, 405))
        self.assertNoWriteHappened()

    def test_redirects_when_no_shop_warehouse_is_configured(self):
        Warehouse.objects.filter(is_shop=True).update(is_shop=False)
        response = self.client.get(reverse('sales:sale_create'))
        self.assertRedirects(response, reverse('core:dashboard'))

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('sales:sale_create'))
        self.assertEqual(response.status_code, 302)
